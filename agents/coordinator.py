"""
Coordinator - Multi-agent orchestrator for goal-driven execution.

Runs the perceive → decide → act → verify loop with:
- Retry ladder escalation before LLM replan (W10)
- Pre-action snapshot for accurate verification (W1)
- Post-gesture stabilization via VerifierAgent (W4)
- Error screen detection via VerifierAgent (W5)
- Screen-aware planning via PlannerAgent (W7)
- State flush on replan (W8)
"""

import asyncio
import uuid
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from aura_graph.agent_state import (
    Goal, RetryStrategy, RETRY_LADDER, Subgoal, StepMemory,
)
from config.success_criteria import get_success_criteria
from services.ui_signature import compute_ui_signature, signatures_differ
from utils.logger import get_logger
from services.command_logger import get_command_logger

if TYPE_CHECKING:
    from agents.actor_agent import ActorAgent
    from agents.perceiver_agent import PerceiverAgent, ScreenState
    from agents.planner_agent import PlannerAgent
    from agents.verifier_agent import VerifierAgent
    from perception.models import PerceptionBundle
    from services.reactive_step_generator import ReactiveStepGenerator
    from services.task_progress import TaskProgressService

logger = get_logger(__name__)

MAX_TOTAL_ACTIONS = 30
MAX_REPLAN_ATTEMPTS = 3

# Commit actions that produce side-effects and need VLM verification
COMMIT_ACTIONS = {
    "add to cart", "buy", "purchase", "send", "submit",
    "place order", "checkout", "pay", "confirm", "delete", "remove",
}

# Actions that don't require a target element on screen
NO_TARGET_ACTIONS = {
    "open_app", "go_back", "go_home", "back", "home",
    "scroll", "scroll_up", "scroll_down", "scroll_left", "scroll_right",
    "swipe", "volume_up", "volume_down", "type",
    "type_text", "enter_text", "set_text", "input_text",
    "press_enter", "press_search", "dismiss_keyboard",
    "wait", "none",
}

_MEDIA_STATE_KW = ("playing", "pause", "paused", "now playing")


def _media_state_summary(elements: list) -> str:
    """Return a compact string of playback/state indicators from the element tree.

    Scans contentDescription fields for media-state keywords so the next VLM
    turn can verify the previous action's outcome without guessing.
    """
    hits: list[str] = []
    seen: set[str] = set()
    for el in (elements or []):
        cd = (el.get("contentDescription") or "").strip()
        if cd and cd not in seen and any(kw in cd.lower() for kw in _MEDIA_STATE_KW):
            hits.append(cd[:60])
            seen.add(cd)
            if len(hits) >= 3:
                break
    return " | ".join(hits) if hits else ""


# ── Goal type keywords for heuristic completion detection ────────────────
_MEDIA_GOAL_KW = {"play", "music", "song", "track", "album", "playlist", "podcast", "audio", "video", "youtube"}
_NAV_GOAL_KW = {"navigate", "navigation", "directions", "route", "drive to", "take me to", "go to", "how to get"}
_MSG_GOAL_KW = {"send message", "send a message", "text ", "whatsapp", "send email", "send mail"}
_CALL_GOAL_KW = {"call ", "dial ", "phone call"}


def _classify_goal_type(utterance: str) -> str:
    """Classify goal into a category for heuristic completion detection."""
    u = utterance.lower()
    if any(kw in u for kw in _MEDIA_GOAL_KW):
        return "media"
    if any(kw in u for kw in _NAV_GOAL_KW):
        return "navigation"
    if any(kw in u for kw in _MSG_GOAL_KW):
        return "messaging"
    if any(kw in u for kw in _CALL_GOAL_KW):
        return "call"
    return "other"


def _detect_goal_completion(utterance: str, elements: list, pre_elements: list | None = None) -> tuple[bool, str]:
    """Deterministic UI-tree heuristic for goal completion.

    Checks post-action element tree for strong completion signals that don't
    require a VLM call:
    - Media goals: Pause button visible = playback active
    - Navigation goals: live navigation view (ETA, End, no Start button)
    - Messaging goals: Sent/Delivered indicator
    - Call goals: calling screen active

    Args:
        pre_elements: UI elements captured BEFORE the action. When provided,
            weak signals already present before the action are ignored to
            avoid false positives from pre-existing media playback.

    Returns:
        (is_complete, reason) — reason is empty when not complete.
    """
    goal_type = _classify_goal_type(utterance)
    if goal_type == "other" or not elements:
        return False, ""

    # Build searchable text from the first 40 elements
    _all_text: list[str] = []
    _all_cd: list[str] = []
    for el in elements[:40]:
        _all_text.append((el.get("text") or "").strip().lower())
        _all_cd.append((el.get("contentDescription") or "").strip().lower())

    # Pre-action content descriptions — used to suppress signals already present
    # before the action fired (e.g. a now-playing mini-player that was already visible).
    _pre_cd: set[str] = set()
    if pre_elements:
        for el in pre_elements[:40]:
            cd = (el.get("contentDescription") or "").strip().lower()
            if cd:
                _pre_cd.add(cd)

    if goal_type == "media":
        # Pause button visible = playback is active = DONE
        # This is a strong signal — valid even if pause was already showing.
        pause_signals = ("pause", "\u23f8", "\u2016")
        for cd in _all_cd:
            if any(sig in cd for sig in pause_signals):
                return True, f"Media playing — Pause button detected (cd='{cd}')"
        for txt in _all_text:
            if "pause" == txt or txt.startswith("pause"):
                return True, f"Media playing — Pause button detected (text='{txt}')"
        # "now playing" banner or cd containing "playing" — weaker signal.
        # Only fire if this indicator was NOT already present before the action,
        # otherwise a pre-existing mini-player triggers a false positive.
        for cd in _all_cd:
            if "now playing" in cd or (cd.startswith("playing") and len(cd) > 8):
                if cd not in _pre_cd:
                    return True, f"Media playing — now playing indicator (cd='{cd}')"

    elif goal_type == "navigation":
        # After pressing Start: look for active navigation signals
        has_start = any("start" in t for t in _all_text) or any("start" in c for c in _all_cd)
        has_nav_signals = False
        nav_evidence = ""
        nav_indicators = ("end", "mute", "eta", "min", "arrival", "head ", "turn ", "reroute", "exit navigation")
        for cd in _all_cd:
            if any(ind in cd for ind in nav_indicators):
                has_nav_signals = True
                nav_evidence = f"cd='{cd}'"
                break
        if not has_nav_signals:
            for txt in _all_text:
                if any(ind in txt for ind in nav_indicators):
                    has_nav_signals = True
                    nav_evidence = f"text='{txt}'"
                    break
        if has_nav_signals and not has_start:
            return True, f"Navigation active — {nav_evidence}, Start button gone"

    elif goal_type == "messaging":
        sent_signals = ("sent", "delivered", "message sent", "email sent")
        for txt in _all_text:
            if any(sig in txt for sig in sent_signals):
                return True, f"Message sent — indicator detected (text='{txt}')"
        for cd in _all_cd:
            if any(sig in cd for sig in sent_signals):
                return True, f"Message sent — indicator detected (cd='{cd}')"

    elif goal_type == "call":
        call_signals = ("calling", "ringing", "on call", "dialing", "ongoing call")
        for txt in _all_text:
            if any(sig in txt for sig in call_signals):
                return True, f"Call active — indicator detected (text='{txt}')"
        for cd in _all_cd:
            if any(sig in cd for sig in call_signals):
                return True, f"Call active — indicator detected (cd='{cd}')"

    return False, ""


class Coordinator:
    """
    Orchestrate PlannerAgent, PerceiverAgent, ActorAgent, and VerifierAgent
    through a goal-driven execution loop.
    """

    def __init__(
        self,
        planner: "PlannerAgent",
        perceiver: "PerceiverAgent",
        actor: "ActorAgent",
        verifier: "VerifierAgent",
        task_progress: "TaskProgressService",
        reactive_gen: Optional["ReactiveStepGenerator"] = None,
    ):
        self.planner = planner
        self.perceiver = perceiver
        self.actor = actor
        self.verifier = verifier
        self.task_progress = task_progress
        self.reactive_gen = reactive_gen

    async def execute(
        self,
        utterance: str,
        intent: Dict[str, Any],
        session_id: str,
        perception_bundle: Optional["PerceptionBundle"] = None,
    ) -> Dict[str, Any]:
        """
        Execute a user goal end-to-end.

        Args:
            utterance: Original user request.
            intent: Parsed intent dict.
            session_id: Session identifier.
            perception_bundle: Optional pre-captured perception.

        Returns:
            Dict with status, goal, executed_steps, total_actions, error.
        """
        executed_steps: List[Dict[str, Any]] = []
        step_memory: List[StepMemory] = []
        total_actions = 0
        screen_hash_history: List[str] = []
        action_coord_history: List[tuple] = []  # (action_type, x, y) for loop detection
        replan_count = 0
        recovery_injection_count = 0
        consecutive_gesture_failures = 0
        running_screen_context = ""
        _cmd_logger = get_command_logger()

        # --- Plan ---
        # W7 fix: pass current screen context to planner
        self.task_progress.emit_agent_status("Planner", f"Planning: {utterance[:50]}")
        goal = self.planner.create_plan(utterance, intent, perception=perception_bundle, step_history=step_memory)

        # Seed running_screen_context from the initial perception bundle so the
        # first reactive step generation has something grounding to work with.
        if perception_bundle:
            _vd = getattr(perception_bundle, "visual_description", None)
            if _vd:
                running_screen_context = _vd[:800]
            elif getattr(perception_bundle, "ui_tree", None) and perception_bundle.ui_tree.elements:
                _labels = [
                    (e.get("text") or e.get("contentDescription") or "").strip()
                    for e in perception_bundle.ui_tree.elements[:8]
                ]
                running_screen_context = "; ".join(l for l in _labels if l)[:800]

        if goal.phases:
            logger.info(
                f"Coordinator: skeleton plan — {goal.description} "
                f"({len(goal.phases)} phases, commits={goal.pending_commits})"
            )
            _cmd_logger.log_agent_decision("PLAN_CREATED", {
                "goal": goal.description,
                "mode": "reactive",
                "phases": [p.description for p in goal.phases],
                "commit_actions": goal.pending_commits,
            }, agent_name="Planner")
        else:
            logger.info(f"Coordinator: static plan — {goal.description} ({len(goal.subgoals)} subgoals)")
            _cmd_logger.log_agent_decision("PLAN_CREATED", {
                "goal": goal.description,
                "mode": "static",
                "total_subgoals": len(goal.subgoals),
                "subgoals": [
                    {"index": i + 1, "description": sg.description, "action_type": sg.action_type, "target": sg.target}
                    for i, sg in enumerate(goal.subgoals)
                ],
            }, agent_name="Planner")

        if goal.phases:
            self.task_progress.emit_agent_status("Planner", f"Plan ready: {len(goal.phases)} phases")
        else:
            self.task_progress.emit_agent_status("Planner", f"Plan ready: {len(goal.subgoals)} steps")

        # Broadcast task start
        self._broadcast_start(session_id, goal)

        # --- Subgoal loop ---
        while True:
            # Check for user cancellation
            if self.task_progress.is_cancelled(session_id):
                goal.aborted = True
                goal.abort_reason = "Cancelled by user"
                logger.warning("Coordinator: task cancelled by user")
                break

            subgoal = goal.current_subgoal

            # ── Reactive step generation ───────────────────────────────────────────────────
            # When no concrete subgoal is pending we either: (a) complete the
            # goal if all phases are done / no phases exist (legacy mode), or
            # (b) ask the reactive generator for the next grounded step.
            if subgoal is None:
                if not goal.phases:
                    # Legacy / static-plan mode: all pre-baked subgoals executed.
                    goal.completed = True
                    break
                if not goal.current_phase:
                    # All skeleton phases exhausted.
                    goal.completed = True
                    break
                if total_actions >= MAX_TOTAL_ACTIONS:
                    goal.aborted = True
                    goal.abort_reason = "Action budget exhausted"
                    logger.warning("Coordinator: budget exhausted")
                    _cmd_logger.log_agent_decision("BUDGET_EXHAUSTED", {
                        "total_actions": total_actions,
                        "max_actions": MAX_TOTAL_ACTIONS,
                        "current_phase": goal.current_phase.description,
                    }, agent_name="Coordinator")
                    break
                if self.reactive_gen is None:
                    # No reactive generator wired up — fall back to completion.
                    logger.warning("Coordinator: reactive_gen not set, completing goal")
                    goal.completed = True
                    break

                # ── Short-circuit: "Open <App>" phases ─────────────────────
                # When the phase is just "Open <App>", skip the VLM call
                # entirely and create an open_app subgoal directly.  This
                # avoids the VLM hallucinating a tap on the wrong icon and
                # ensures the app is launched via package name every time.
                _phase_desc = goal.current_phase.description.strip()
                _open_app_name = self._extract_open_app_phase(_phase_desc)
                if _open_app_name:
                    # Check if already in the target app (avoid redundant launch)
                    _already_in_app = False
                    try:
                        _bundle = await self.perceiver.perception_controller.request_perception(
                            intent=intent, action_type="verify",
                            force_screenshot=False, skip_description=True,
                        )
                        if _bundle and _bundle.ui_tree:
                            from utils.app_inventory_utils import get_app_inventory_manager
                            _fg_pkg = _bundle.ui_tree.source_package
                            _candidates = get_app_inventory_manager().get_package_candidates(
                                _open_app_name.lower().strip()
                            )
                            if _fg_pkg and _fg_pkg in _candidates:
                                _already_in_app = True
                    except Exception:
                        pass

                    if _already_in_app:
                        logger.info(f"Coordinator: already in '{_open_app_name}' — skipping open_app phase")
                        goal.advance_phase()
                        _cmd_logger.log_agent_decision("PHASE_COMPLETE", {
                            "phase": _phase_desc,
                            "reason": "already_in_app",
                            "foreground_package": _fg_pkg,
                        }, agent_name="Coordinator")
                        continue

                    logger.info(f"Coordinator: short-circuit open_app for '{_open_app_name}' (no VLM needed)")
                    criteria = get_success_criteria("open_app")
                    criteria.target_screen_reached = _open_app_name.lower()
                    next_step = Subgoal(
                        description=f"Open {_open_app_name}",
                        action_type="open_app",
                        target=_open_app_name,
                        success_criteria=criteria,
                    )
                    next_step.parameters["__phase_complete__"] = True
                    goal._reactive_retries = 0
                    goal.subgoals.append(next_step)
                    _cmd_logger.log_agent_decision("REACTIVE_STEP_GENERATED", {
                        "phase": _phase_desc,
                        "action_type": "open_app",
                        "target": _open_app_name,
                        "description": f"Open {_open_app_name}",
                        "shortcircuit": True,
                    }, agent_name="Coordinator")
                    continue

                # Ask the reactive generator for the next concrete step.
                # Always capture a fresh screenshot + UI elements so the VLM
                # sees the real screen.  This replaces the old two-call pattern
                # (VLM describe_screen → text-only LLM) with a single VLM call
                # that receives screenshot + goal context + UI hints.
                _latest_b64 = ""
                _elements = []
                try:
                    _latest_bundle = await self.perceiver.perception_controller.request_perception(
                        intent=intent, action_type="verify", force_screenshot=True,
                        skip_description=True,
                    )
                    if _latest_bundle:
                        if (_latest_bundle.screenshot
                                and _latest_bundle.screenshot.screenshot_base64):
                            _latest_b64 = _latest_bundle.screenshot.screenshot_base64
                        # Build SoM-annotated screenshot for the VLM so it sees
                        # numbered boxes instead of a plain screen capture.
                        _elements = (_latest_bundle.ui_tree.elements
                                     if _latest_bundle.ui_tree else [])
                        _sw = getattr(_latest_bundle.screen_meta, "width", 1080) or 1080
                        _sh = getattr(_latest_bundle.screen_meta, "height", 1920) or 1920
                        if _latest_b64 and _elements:
                            _latest_b64, _filtered = self.perceiver.build_annotated_screenshot(
                                _latest_b64, _elements, _sw, _sh
                            )
                            if _filtered:
                                _elements = _filtered
                except Exception:
                    pass

                self.task_progress.emit_agent_status("Reactive", f"Generating next step for phase: {goal.current_phase.description[:35] if goal.current_phase else 'final'}")
                next_step = self.reactive_gen.generate_next_step(
                    goal, running_screen_context, step_memory,
                    screenshot_b64=_latest_b64, ui_hints="",
                    ui_elements=_elements,
                )
                if next_step is None:
                    # Likely a parse failure — retry once before giving up on this phase.
                    _reactive_retries = getattr(goal, "_reactive_retries", 0)
                    if _reactive_retries < 2:
                        goal._reactive_retries = _reactive_retries + 1
                        logger.warning(
                            f"Coordinator: reactive step returned None "
                            f"(retry {goal._reactive_retries}/2)"
                        )
                        continue
                    # Retries exhausted — treat as phase complete and move on.
                    goal._reactive_retries = 0
                    prev_phase_desc = goal.current_phase.description
                    goal.advance_phase()
                    logger.info(
                        f"Coordinator: phase '{prev_phase_desc}' complete"
                        f" → {goal.current_phase.description if goal.current_phase else 'all phases done'}"
                    )
                    _cmd_logger.log_agent_decision("PHASE_COMPLETE", {
                        "completed_phase": prev_phase_desc,
                        "next_phase": goal.current_phase.description if goal.current_phase else None,
                    }, agent_name="Coordinator")
                    continue
                # Inject the generated step into the subgoal list.
                goal._reactive_retries = 0

                # Update running_screen_context from the VLM's screen_context
                # output — this replaces the old separate describe_screen call.
                _reactive_ctx = next_step.parameters.get("__screen_context__", "")
                if _reactive_ctx:
                    running_screen_context = str(_reactive_ctx)[:800]

                # If the model flagged the previous step as incorrect (prev_step_ok=false),
                # retroactively patch the last step_memory entry so future reactive steps
                # see "issue_detected" instead of "success" for the botched step.
                # The current next_step is already the corrective action the model chose.
                _prev_issue = next_step.parameters.get("__prev_step_issue__", "")
                if not next_step.parameters.get("__prev_step_ok__", True) and _prev_issue and step_memory:
                    _last_mem = step_memory[-1]
                    logger.warning(
                        f"Coordinator: model flagged prev step '[{_last_mem.action_type}] "
                        f"{_last_mem.subgoal_description[:50]}' as incorrect — {_prev_issue[:100]}"
                    )
                    _last_mem.result = f"issue_detected: {_prev_issue[:100]}"
                    _cmd_logger.log_agent_decision("PREV_STEP_ISSUE_DETECTED", {
                        "flagged_step": _last_mem.subgoal_description[:60],
                        "action_type": _last_mem.action_type,
                        "issue": _prev_issue[:100],
                        "corrective_action": f"[{next_step.action_type}] {next_step.target or ''}",
                    }, agent_name="Reactive")

                # No tap injection needed — the type gesture now carries focus_x/focus_y
                # so Android uses ACTION_ACCESSIBILITY_FOCUS instead of a click.
                # (tap-to-focus was the sole source of keyboard pop-ups during automation)
                _is_type_action = next_step.action_type in (
                    "type", "type_text", "enter_text", "set_text", "input_text"
                )

                goal.subgoals.append(next_step)
                _cmd_logger.log_agent_decision("REACTIVE_STEP_GENERATED", {
                    "phase": goal.current_phase.description if goal.current_phase else "?",
                    "action_type": next_step.action_type,
                    "target": next_step.target,
                    "description": next_step.description,
                }, agent_name="ReactiveStepGen")
                continue
            # ────────────────────────────────────────────────────────────────────

            if total_actions >= MAX_TOTAL_ACTIONS:
                goal.aborted = True
                goal.abort_reason = "Action budget exhausted"
                logger.warning("Coordinator: budget exhausted")
                _cmd_logger.log_agent_decision("BUDGET_EXHAUSTED", {
                    "total_actions": total_actions,
                    "max_actions": MAX_TOTAL_ACTIONS,
                    "last_subgoal": subgoal.description,
                }, agent_name="Coordinator")
                break

            logger.info(f"Coordinator: subgoal {goal.current_subgoal_index + 1}/{len(goal.subgoals)} — {subgoal.description}")
            _cmd_logger.log_agent_decision("SUBGOAL_START", {
                "index": goal.current_subgoal_index + 1,
                "total": len(goal.subgoals),
                "description": subgoal.description,
                "action_type": subgoal.action_type,
                "target": subgoal.target,
                "attempt": subgoal.attempts + 1,
            }, agent_name="Coordinator")
            self.task_progress.emit_agent_status(
                "Aura",
                f"[{goal.current_subgoal_index + 1}/{len(goal.subgoals)}] {subgoal.description[:45]}",
            )

            # --- Decide: does this action need perception at all? ---
            action_type = subgoal.action_type
            coordinates = None
            screen_state = None

            # Build plan context: show current phase + executed history
            if goal.phases:
                _done = [sg for sg in goal.subgoals if sg.completed]
                _phase_str = f"Phase: {goal.current_phase.description}" if goal.current_phase else "Final phase"
                plan_context = (
                    f"Goal: {goal.original_utterance}\n"
                    f"{_phase_str}\n"
                    "Executed: "
                    + "; ".join(f"[{sg.action_type}] {sg.description}" for sg in _done[-5:])
                )
            else:
                plan_context = "\n".join(
                    f"{i+1}. [{sg.action_type}] {sg.description} → {sg.target or '-'}"
                    for i, sg in enumerate(goal.subgoals)
                )

            if action_type in NO_TARGET_ACTIONS:
                # No UI element to locate — skip perception entirely.
                # This prevents unnecessary UI-tree fetches and OmniParser calls
                # for open_app, type, press_enter, scroll, etc.
                logger.debug(f"Coordinator: skipping perception for no-target action '{action_type}'")
            else:
                # --- Perceive ---
                self.task_progress.emit_agent_status("Perceiver", f"Scanning screen for '{subgoal.target or subgoal.description[:30]}'")
                try:
                    screen_state = await self.perceiver.perceive(
                        subgoal, intent, step_history=step_memory,
                        user_command=utterance,
                        plan_context=plan_context,
                    )
                except Exception as e:
                    logger.error(f"Coordinator: perception failed — {e}")
                    _cmd_logger.log_agent_decision("PERCEPTION_FAILED", {
                        "subgoal": subgoal.description,
                        "error": str(e),
                    }, agent_name="Perceiver")
                    goal.aborted = True
                    goal.abort_reason = f"Perception failed: {e}"
                    break

                # Log perception result with screenshot and UI elements
                try:
                    ss_path = ""
                    omni_path = getattr(_cmd_logger, "_last_omniparser_screenshot", "") or ""
                    if omni_path:
                        _cmd_logger._last_omniparser_screenshot = ""  # consume it
                    bundle = screen_state.perception_bundle
                    ann_path = ""
                    highlighted_path = ""
                    if bundle and bundle.screenshot and bundle.screenshot.screenshot_base64:
                        ss_path = _cmd_logger.log_screenshot(
                            label=f"screen_{subgoal.description[:30]}",
                            base64_data=bundle.screenshot.screenshot_base64,
                        )
                        if screen_state.vlm_annotated_b64:
                            ann_path = _cmd_logger.log_screenshot(
                                label=f"screen_{subgoal.description[:26]}_ann",
                                base64_data=screen_state.vlm_annotated_b64,
                            )
                        else:
                            ann_path = _cmd_logger.log_annotated_screenshot(
                                label=f"screen_{subgoal.description[:26]}_ann",
                                base64_data=bundle.screenshot.screenshot_base64,
                                elements=screen_state.elements or [],
                                target_match=screen_state.target_match,
                            )
                        if screen_state.highlighted_b64:
                            highlighted_path = _cmd_logger.log_screenshot(
                                label=f"screen_{subgoal.description[:24]}_hl",
                                base64_data=screen_state.highlighted_b64,
                            )
                    if screen_state.screen_description:
                        running_screen_context = screen_state.screen_description
                    elif screen_state.elements:
                        # Prefer last known VLM description over raw labels — the ReactiveStep LLM
                        # needs meaningful screen context even on fast-path iterations where
                        # describe_screen() was skipped (open_app, scroll, etc.)
                        last_vlm = next(
                            (m.screen_description for m in reversed(step_memory) if m.screen_description),
                            None,
                        )
                        if last_vlm:
                            running_screen_context = f"[prev screen] {last_vlm[:700]}"
                        else:
                            _elem_labels = [
                                (e.get("text") or e.get("contentDescription") or "").strip()
                                for e in screen_state.elements[:8]
                                if (e.get("text") or e.get("contentDescription") or "").strip()
                            ]
                            if _elem_labels:
                                running_screen_context = "; ".join(_elem_labels[:6])
                    _cmd_logger.log_agent_decision("PERCEPTION_RESULT", {
                        "subgoal": subgoal.description,
                        "replan_suggested": screen_state.replan_suggested,
                        "replan_reason": screen_state.replan_reason,
                        "screen_type": screen_state.screen_type,
                        "element_count": len(screen_state.elements),
                        "elements_summary": [
                            {
                                "index": i + 1,
                                "text": e.get("text", "")[:80],
                                "content_desc": (e.get("contentDescription") or "")[:60],
                                "class": (e.get("className") or e.get("class_name") or ""),
                                "resource_id": (e.get("resourceId") or "").split("/")[-1],
                                "bounds": e.get("bounds") or e.get("visibleBounds") or {},
                                "clickable": e.get("clickable", False),
                                "scrollable": e.get("scrollable", False),
                                "editable": e.get("editable", False) or e.get("inputText", False),
                                "focused": e.get("focused", False),
                                "enabled": e.get("enabled", True),
                            }
                            for i, e in enumerate(screen_state.elements or [])
                        ],
                        "target_match": screen_state.target_match,
                        "element_description": screen_state.element_description or "",
                        "screen_description": screen_state.screen_description,
                        "screenshot_path": ss_path,
                        "annotated_screenshot_path": ann_path,
                        "omniparser_screenshot_path": omni_path,
                        "highlighted_element_path": highlighted_path,
                    }, agent_name="Perceiver")
                except Exception:
                    pass

            # VLM flagged wrong screen — trigger adaptive replan immediately
            if screen_state and screen_state.replan_suggested and screen_state.replan_reason:
                replan_count += 1
                if replan_count <= MAX_REPLAN_ATTEMPTS:
                    self.task_progress.emit_agent_status("Planner", f"Replanning: {screen_state.replan_reason[:40]}")
                    obstacle = f"Wrong screen for this step. {screen_state.replan_reason}"
                    new_subgoals = self.planner.replan(
                        goal, obstacle,
                        perception=screen_state.perception_bundle,
                        step_history=step_memory,
                    )
                    self._apply_replan(goal, new_subgoals)
                    _cmd_logger.log_agent_decision("ADAPTIVE_REPLAN", {
                        "reason": "screen_mismatch",
                        "vlm_deviation": screen_state.replan_reason,
                        "replan_count": replan_count,
                        "new_subgoal_count": len(new_subgoals),
                    }, agent_name="Planner")
                    self._broadcast_start(session_id, goal)
                    continue

            if action_type in NO_TARGET_ACTIONS:
                # Already decided above — no coordinates needed
                pass
            elif screen_state and screen_state.target_match:
                coordinates = (screen_state.target_match["x"], screen_state.target_match["y"])
            else:
                # Target not found — try retry ladder
                retry_outcome = await self._handle_target_not_found(
                    subgoal, intent, screen_state, goal,
                    executed_steps, total_actions, screen_hash_history,
                    step_memory=step_memory,
                )
                if retry_outcome == "found":
                    # Re-perceive succeeded — restart this subgoal iteration
                    continue
                elif retry_outcome == "replan":
                    replan_count += 1
                    if replan_count > MAX_REPLAN_ATTEMPTS:
                        goal.aborted = True
                        goal.abort_reason = "Max replan attempts exceeded"
                        break
                    # W8 fix: flush stale state
                    screen_hash_history.clear()
                    _labels = []
                    if screen_state:
                        for _el in (screen_state.elements or [])[:20]:
                            _lbl = ((_el.get("text") or "").strip()
                                    or (_el.get("contentDescription") or "").strip())
                            if _lbl:
                                _labels.append(_lbl)
                    obstacle = (
                        f"Cannot find '{subgoal.target}' on screen after scrolling. "
                        f"Visible elements: {_labels[:15]}. "
                        f"Screen: {(screen_state.screen_description if screen_state else None) or running_screen_context or 'unknown'}."
                    )
                    new_subgoals = self.planner.replan(
                        goal, obstacle,
                        perception=screen_state.perception_bundle if screen_state else None,
                        step_history=step_memory,
                    )
                    self._apply_replan(goal, new_subgoals)
                    _cmd_logger.log_agent_decision("REPLAN", {
                        "reason": "target_not_found",
                        "obstacle": obstacle,
                        "replan_count": replan_count,
                        "new_subgoal_count": len(new_subgoals),
                    }, agent_name="Planner")
                    self._broadcast_start(session_id, goal)
                    continue
                else:
                    # Abort
                    goal.aborted = True
                    goal.abort_reason = f"Target '{subgoal.target}' not found and retries exhausted"
                    _cmd_logger.log_agent_decision("TARGET_NOT_FOUND", {
                        "target": subgoal.target,
                        "subgoal": subgoal.description,
                        "attempts": subgoal.attempts,
                    }, agent_name="Perceiver")
                    break

            # Flag commit actions for VLM verification.
            # Also flag any action on a WebView screen — the accessibility tree is
            # unreliable there and screen_changed alone can be a false positive.
            # Key-press actions (press_enter, press_search) are NOT commit actions —
            # their success is determined by screen_changed alone, not VLM confirmation.
            if (
                (any(kw in subgoal.description.lower() for kw in COMMIT_ACTIONS)
                 or (screen_state and screen_state.screen_type == "webview"))
                and subgoal.action_type not in ("press_enter", "press_search", "dismiss_keyboard")
            ):
                subgoal.requires_vlm_verify = True
                if screen_state:
                    cart_count = self._extract_cart_count(screen_state)
                    # Also save the pre-action screenshot for before/after VLM comparison
                    pre_b64 = ""
                    bundle = screen_state.perception_bundle
                    if bundle and bundle.screenshot and bundle.screenshot.screenshot_base64:
                        pre_b64 = bundle.screenshot.screenshot_base64
                    subgoal.pre_action_context = {
                        "cart_count": cart_count,
                        "pre_screenshot_b64": pre_b64,
                    }

            # --- Snapshot pre-action (W1 fix) ---
            pre_signature = await self._snapshot_pre(intent)

            # --- Act ---
            # Fallback for press_enter: if the previous attempt didn't change the
            # screen, try press_search (keyevent 84 = IME_ACTION_SEARCH) on the
            # first retry, then tap the actual search/submit button on retry 2+.
            effective_action = action_type
            effective_coordinates = coordinates
            if action_type == "press_enter" and subgoal.attempts == 1:
                effective_action = "press_search"
                logger.info("Coordinator: press_enter retry → trying press_search (keyevent 84)")
            elif action_type == "press_enter" and subgoal.attempts >= 2:
                # screen_state is None since press_enter skips perception — fetch a fresh UI tree
                try:
                    fresh_state = await self.perceiver.perceive(
                        subgoal, intent, step_history=step_memory,
                        user_command=utterance, plan_context=plan_context,
                    )
                    elements = fresh_state.elements or []
                except Exception:
                    elements = []
                search_coords = self._find_search_submit_coords(elements)
                if search_coords:
                    effective_action = "tap"
                    effective_coordinates = search_coords
                    logger.info(f"Coordinator: press_enter retry → tapping search button at {search_coords}")

            target_value = subgoal.target if effective_action in ("type", "type_text", "enter_text", "set_text", "input_text", "open_app") else None

            # Pre-type focus check: ensure the CORRECT input field is focused before typing
            if effective_action in ("type", "type_text", "enter_text", "set_text", "input_text") and target_value:
                from services.ui_tree_service import get_ui_tree_service
                _ui_svc = get_ui_tree_service()
                try:
                    _pre_req = f"type_focus_{uuid.uuid4().hex[:8]}"
                    _pre_tree = await _ui_svc.request_ui_tree(_pre_req, "pre_type_focus_check")
                    _all_elements = _pre_tree.elements if _pre_tree and _pre_tree.elements else []
                    _all_edits: List[Dict] = []
                    _focused_edit = None
                    for _el in _all_elements:
                        if self._is_input_element(_el):
                            _all_edits.append(_el)
                            if _el.get("focused") or _el.get("isFocused"):
                                _focused_edit = _el

                    # Determine WHICH field to focus: match via field_hint or description
                    _field_hint = subgoal.parameters.get("__field_hint__", "")
                    _intended_edit = self._match_intended_edit_field(
                        _field_hint, subgoal.description, _all_edits, all_elements=_all_elements
                    )

                    # Always determine the target field and embed its coords
                    # so Android uses ACTION_ACCESSIBILITY_FOCUS on the right node
                    # (even when the field *appears* focused — without a tap there
                    #  is no real INPUT focus so Strategy 0 on Android is essential).
                    _target_el = None
                    if _intended_edit is not None:
                        _target_el = _intended_edit
                    elif _focused_edit:
                        _target_el = _focused_edit
                    elif _all_edits:
                        _target_el = _all_edits[0]

                    if _target_el is not None:
                        _bounds = _target_el.get("bounds", {})
                        _cx = (_bounds.get("left", 0) + _bounds.get("right", 0)) // 2
                        _cy = (_bounds.get("top", 0) + _bounds.get("bottom", 0)) // 2
                        if _cx > 0 and _cy > 0:
                            _field_label = (
                                _field_hint
                                or (_target_el.get("hint") or "")
                                or (_target_el.get("contentDescription") or "")
                                or "input field"
                            )[:40]
                            logger.info(
                                f"Coordinator: embedding focus coords ({_cx},{_cy}) for field '{_field_label}' — no tap"
                            )
                            _cmd_logger.log_agent_decision("FOCUS_COORDS_EMBEDDED", {
                                "field_hint": _field_hint,
                                "field_label": _field_label,
                                "coords": (_cx, _cy),
                                "was_focused": _focused_edit is not None,
                                "field_count": len(_all_edits),
                            }, agent_name="Coordinator")
                            # Embed into the subgoal parameters — gesture_executor passes these
                            # to Android as focus_x/focus_y so it uses ACTION_ACCESSIBILITY_FOCUS
                            # instead of a tap (keyboard never opens).
                            subgoal.parameters["focus_x"] = _cx
                            subgoal.parameters["focus_y"] = _cy

                    elif not _focused_edit and not _all_edits:
                        # No EditText in the accessibility tree. This happens for canvas/vision-mode
                        # apps (e.g. Google Maps) where the field exists visually but isn't exposed
                        # to the accessibility service. Attempt to locate and tap the field from a
                        # screenshot before typing — otherwise Android has nothing to type into.
                        _field_hint_vt = subgoal.parameters.get("__field_hint__", "")
                        _tap_target = _field_hint_vt or subgoal.description or "input field"
                        _tapped_visually = False
                        if self.perceiver.vlm_service:
                            try:
                                _focus_state = await self.perceiver.perceive(
                                    subgoal, intent, force_screenshot=True,
                                    step_history=step_memory,
                                    user_command=utterance, plan_context=plan_context,
                                )
                                _focus_bundle = _focus_state.perception_bundle if _focus_state else None
                                # Reuse target_match from perceive() if already located — avoids
                                # a duplicate VLMSelector call for the same field.
                                _vl_result = None
                                if (
                                    _focus_state
                                    and _focus_state.target_match
                                    and _focus_state.target_match.get("x")
                                ):
                                    _vl_result = _focus_state.target_match
                                    logger.info(
                                        f"Coordinator: reusing perceive() target_match "
                                        f"({_vl_result['x']},{_vl_result['y']}) — skipping duplicate locate_from_bundle"
                                    )
                                elif _focus_bundle:
                                    _vl_result = self.perceiver.locate_from_bundle(
                                        _focus_bundle, _tap_target,
                                        screen_context=running_screen_context,
                                        subgoal_description=subgoal.description,
                                    )
                                if _vl_result:
                                    _tx, _ty = int(_vl_result["x"]), int(_vl_result["y"])
                                    logger.info(
                                        f"Coordinator: vision-mode pre-tap ({_tx},{_ty}) "
                                        f"to focus '{_tap_target[:40]}' before type"
                                    )
                                    _cmd_logger.log_agent_decision("VISION_MODE_PRE_TAP", {
                                        "field_hint": _field_hint_vt,
                                        "coords": (_tx, _ty),
                                        "source": _vl_result.get("source", "vlm"),
                                    }, agent_name="Coordinator")
                                    await self.actor.execute(
                                        "tap",
                                        coordinates=(_tx, _ty),
                                        parameters={"format": "pixels"},
                                    )
                                    await asyncio.sleep(0.6)  # wait for field focus / keyboard
                                    _tapped_visually = True
                            except Exception as _vte:
                                logger.warning(f"Coordinator: vision-mode pre-tap failed: {_vte}")

                        if not _tapped_visually:
                            # No EditText and visual locate failed — type will likely fail
                            logger.warning("Coordinator: no input field on screen — skipping type action")
                            _cmd_logger.log_agent_decision("TYPE_SKIPPED_NO_INPUT_FIELD", {
                                "target": target_value,
                                "subgoal": subgoal.description,
                            }, agent_name="Coordinator")
                            step_memory.append(StepMemory(
                                subgoal_description=subgoal.description,
                                action_type=action_type,
                                target=subgoal.target,
                                result="failed: no input field on screen — tap a search icon or text field first",
                                screen_type=screen_state.screen_type if screen_state else "unknown",
                                screen_before=pre_signature,
                                screen_after=pre_signature,
                                coordinates=None,
                            ))
                            subgoal.attempts += 1
                            if subgoal.attempts >= 3:
                                goal.advance_subgoal()
                                self._broadcast_step(session_id, success=False)
                            consecutive_gesture_failures += 1
                            if consecutive_gesture_failures >= 6:
                                goal.aborted = True
                                goal.abort_reason = f"No input field on screen after {consecutive_gesture_failures} attempts"
                                break
                            continue
                except Exception as e:
                    logger.warning(f"Coordinator: pre-type focus check failed: {e}")

                # Also check if EditText already contains the intended text
                _skip_type_dup = False
                try:
                    _dup_req = f"type_pre_{uuid.uuid4().hex[:8]}"
                    _dup_tree = await _ui_svc.request_ui_tree(_dup_req, "pre_type_dup_check")
                    for _el in (_dup_tree.elements if _dup_tree and _dup_tree.elements else []):
                        if self._is_input_element(_el):
                            _el_text = (_el.get("text") or "").strip()
                            if target_value.strip().lower() in _el_text.lower():
                                logger.info(f"Coordinator: skipping type — EditText already contains '{target_value[:40]}'")
                                _cmd_logger.log_agent_decision("TYPE_SKIPPED_ALREADY_TYPED", {
                                    "target": target_value,
                                    "subgoal": subgoal.description,
                                }, agent_name="Coordinator")
                                step_memory.append(StepMemory(
                                    subgoal_description=subgoal.description,
                                    action_type=action_type,
                                    target=subgoal.target,
                                    result="success",
                                    screen_type="unknown",
                                    screen_before=pre_signature,
                                    screen_after=pre_signature,
                                    coordinates=None,
                                ))
                                goal.advance_subgoal()
                                self._broadcast_step(session_id, success=True)
                                _skip_type_dup = True
                                break
                except Exception:
                    pass
                if _skip_type_dup:
                    continue

            action_result = await self.actor.execute(
                action_type=effective_action,
                target=target_value,
                coordinates=effective_coordinates,
                parameters=subgoal.parameters,
            )
            total_actions += 1

            # --- Post-action screenshot + logcat for debugging (human-only, not fed to VLM) ---
            try:
                from agents.verifier_agent import get_settle_delay
                await asyncio.sleep(get_settle_delay(effective_action))  # action-aware settle before capture
                post_bundle = await self.perceiver.perception_controller.request_perception(
                    intent=intent, action_type="verify", force_screenshot=True,
                )
                if post_bundle and post_bundle.screenshot and post_bundle.screenshot.screenshot_base64:
                    ss_path = _cmd_logger.log_screenshot(
                        label=f"post_{effective_action}_{subgoal.description[:25]}",
                        base64_data=post_bundle.screenshot.screenshot_base64,
                    )
                    _cmd_logger.log_agent_decision("POST_ACTION_SCREENSHOT", {
                        "subgoal": subgoal.description,
                        "action_type": effective_action,
                        "screenshot_path": ss_path,
                    }, agent_name="Perceiver")
            except Exception:
                pass  # screenshot capture is best-effort

            try:
                from services.logcat_capture import get_logcat_capture
                logcat_lines = get_logcat_capture().get_recent(max_lines=30)
                if logcat_lines:
                    _cmd_logger.log_logcat_snapshot(
                        f"post_action:{effective_action}:{subgoal.description[:30]}", logcat_lines
                    )
            except Exception:
                pass

            step_record = {
                "action_type": action_type,
                "target": subgoal.target,
                "coordinates": coordinates,
                "success": action_result.success,
                "duration_ms": action_result.duration_ms,
                "error": action_result.error,
                "subgoal": subgoal.description,
            }
            executed_steps.append(step_record)

            if not action_result.success:
                logger.warning(f"Coordinator: action failed — {action_result.error}")
                consecutive_gesture_failures += 1
                _cmd_logger.log_agent_decision("ACTION_FAILED", {
                    "subgoal": subgoal.description,
                    "action_type": action_type,
                    "error": action_result.error,
                    "attempt": subgoal.attempts + 1,
                    "consecutive_failures": consecutive_gesture_failures,
                }, agent_name="Actor")
                # Abort early if the same kind of failure keeps repeating
                if consecutive_gesture_failures >= 6:
                    goal.aborted = True
                    goal.abort_reason = (
                        f"Aborting after {consecutive_gesture_failures} consecutive gesture failures "
                        f"(last: [{action_type}] {subgoal.description})"
                    )
                    logger.error(f"Coordinator: {goal.abort_reason}")
                    _cmd_logger.log_agent_decision("CONSECUTIVE_FAILURES_ABORT", {
                        "consecutive_failures": consecutive_gesture_failures,
                        "last_action": action_type,
                        "last_target": subgoal.target,
                    }, agent_name="Coordinator")
                    break
                # Record failure in step_memory so the reactive LLM sees LAST FAILURE
                step_memory.append(StepMemory(
                    subgoal_description=subgoal.description,
                    action_type=action_type,
                    target=subgoal.target,
                    result=f"failed: {action_result.error or 'gesture dispatch failed'}",
                    screen_type=screen_state.screen_type if screen_state else "unknown",
                    screen_before=pre_signature,
                    screen_after="",
                    coordinates=coordinates,
                    screen_description=running_screen_context[:200] if running_screen_context else None,
                ))
                subgoal.attempts += 1
                if subgoal.attempts >= 3:
                    # If this subgoal flagged phase completion (e.g. a `wait`/`none`
                    # whose action failed), honour the phase advance so we don't
                    # restart the same phase and re-issue the completed action.
                    if subgoal.parameters.get("__phase_complete__"):
                        goal.advance_phase()
                    # Skip to next subgoal on persistent failure
                    goal.advance_subgoal()
                    self._broadcast_step(session_id, success=False)
                continue

            # Any successful action resets the consecutive failure counter
            consecutive_gesture_failures = 0

            # --- Action+coordinate loop detection ---
            # Track (action_type, x, y) tuples; if the same pair repeats 2+ times
            # the agent is stuck tapping the same element in a loop.
            if effective_coordinates:
                _ac_key = (effective_action, effective_coordinates[0], effective_coordinates[1])
                action_coord_history.append(_ac_key)
                _ac_count = action_coord_history.count(_ac_key)
                if _ac_count >= 3:
                    logger.warning(
                        f"Coordinator: action+coord loop detected — "
                        f"{_ac_key} repeated {_ac_count} times, breaking via scroll+replan"
                    )
                    _cmd_logger.log_agent_decision("ACTION_COORD_LOOP_DETECTED", {
                        "action": effective_action,
                        "coordinates": list(effective_coordinates),
                        "repeat_count": _ac_count,
                        "subgoal": subgoal.description,
                    }, agent_name="Coordinator")
                    # Try scrolling to reveal fresh content
                    await self.actor.execute("scroll", parameters={"direction": "down"})
                    total_actions += 1
                    action_coord_history.clear()

                    # Try text-match fallback against full element list
                    _fallback_found = False
                    if subgoal.target and screen_state and screen_state.elements:
                        _target_lower = subgoal.target.lower()
                        for _el in screen_state.elements:
                            _txt = (_el.get("text") or "").strip().lower()
                            _desc = (_el.get("contentDescription") or "").strip().lower()
                            if _target_lower in _txt or _target_lower in _desc:
                                _b = _el.get("bounds") or _el.get("visibleBounds") or _el.get("boundsInScreen") or {}
                                _fx = (_b.get("left", 0) + _b.get("right", 0)) // 2
                                _fy = (_b.get("top", 0) + _b.get("bottom", 0)) // 2
                                if _fx > 0 and _fy > 0 and (_fx, _fy) != effective_coordinates:
                                    logger.info(f"Coordinator: text-match fallback found '{subgoal.target}' at ({_fx}, {_fy})")
                                    await self.actor.execute("tap", coordinates=(_fx, _fy), parameters={})
                                    total_actions += 1
                                    _fallback_found = True
                                    break

                    if not _fallback_found:
                        # Replan — the current approach is stuck
                        replan_count += 1
                        if replan_count > MAX_REPLAN_ATTEMPTS:
                            goal.aborted = True
                            goal.abort_reason = "Action+coord loop: max replan attempts exceeded"
                            break
                        screen_hash_history.clear()
                        obstacle = (
                            f"Stuck in action loop: tapping ({effective_coordinates}) "
                            f"{_ac_count} times with no progress on '{subgoal.description}'. "
                            f"Screen: {running_screen_context[:200] or 'unknown'}"
                        )
                        new_subgoals = self.planner.replan(
                            goal, obstacle,
                            perception=screen_state.perception_bundle if screen_state else None,
                            step_history=step_memory,
                        )
                        self._apply_replan(goal, new_subgoals)
                        _cmd_logger.log_agent_decision("REPLAN", {
                            "reason": "action_coord_loop",
                            "obstacle": obstacle[:120],
                            "replan_count": replan_count,
                        }, agent_name="Planner")
                        self._broadcast_start(session_id, goal)
                    continue

            # For open_app, the actor already verified the launch via package name check.
            # Skip verifier to avoid false negatives from LLM-generated success hints.
            if action_type == "open_app" and action_result.success:
                logger.info(f"Coordinator: subgoal verified (launch confirmed) — {subgoal.description}")
                _cmd_logger.log_agent_decision("SUBGOAL_COMPLETE", {
                    "subgoal": subgoal.description,
                    "action_type": action_type,
                    "verified_by": "launch_confirmed",
                }, agent_name="Verifier")
                # Wait for the app to finish rendering before the next perception request.
                # Without this delay the UI tree request for the first in-app subgoal
                # fires while the app is still animating and consistently times out.
                logger.info("Coordinator: waiting 3s for app to settle after launch")
                await asyncio.sleep(3.0)

                # Fix: refresh running_screen_context AFTER app launch so the
                # reactive generator sees the real in-app screen, not the stale
                # home-screen context from before open_app.
                _post_launch_screen_type = "unknown"
                try:
                    _post_launch_bundle = await self.perceiver.perception_controller.request_perception(
                        intent=intent,
                        action_type="verify",
                        force_screenshot=True,
                        skip_description=True,
                    )
                    if _post_launch_bundle:
                        _vd = getattr(_post_launch_bundle, "visual_description", None)
                        if _vd:
                            running_screen_context = str(_vd)[:800]
                        elif _post_launch_bundle.ui_tree and _post_launch_bundle.ui_tree.elements:
                            _labels = [
                                (e.get("text") or e.get("contentDescription") or "").strip()
                                for e in _post_launch_bundle.ui_tree.elements[:8]
                            ]
                            running_screen_context = "; ".join(l for l in _labels if l)[:800]
                        _post_launch_screen_type = "native"
                        logger.info(f"Coordinator: post-launch screen context refreshed: {running_screen_context[:80]}")
                except Exception as e:
                    logger.debug(f"Coordinator: post-launch perception failed (non-fatal): {e}")

                step_memory.append(StepMemory(
                    subgoal_description=subgoal.description,
                    action_type=action_type,
                    target=subgoal.target,
                    result="success",
                    screen_type=_post_launch_screen_type,
                    screen_before=pre_signature,
                    screen_after="",
                    coordinates=None,
                ))
                goal.advance_subgoal()
                if subgoal.parameters.get("__phase_complete__") and goal.phases:
                    _prev = goal.current_phase.description if goal.current_phase else "?"
                    goal.advance_phase()
                    logger.info(f"Coordinator: phase complete (open_app) → {goal.current_phase.description if goal.current_phase else 'all done'}")
                self._broadcast_step(session_id, success=True)
                continue

            # --- Verify (W4 stabilization + W5 error detection) ---
            self.task_progress.emit_agent_status("Verifier", f"Checking: {subgoal.description[:40]}")
            post_bundle, post_signature, post_elements = await self.verifier.capture_post_state(intent, action_type=effective_action)
            screen_changed = signatures_differ(pre_signature, post_signature)
            screen_hash_history.append(post_signature)

            # Loop detection: 3+ consecutive identical hashes
            if len(screen_hash_history) >= 3:
                last_three = screen_hash_history[-3:]
                if last_three[0] == last_three[1] == last_three[2]:
                    logger.warning("Coordinator: stuck in loop — 3 identical screens")
                    _cmd_logger.log_agent_decision("LOOP_DETECTED", {
                        "subgoal": subgoal.description,
                        "screen_hash": screen_hash_history[-1][:16] if screen_hash_history else "",
                        "consecutive_identical": 3,
                        "recovery_injection_count": recovery_injection_count,
                    }, agent_name="Coordinator")
                    # Also capture logcat at loop detection
                    try:
                        from services.logcat_capture import get_logcat_capture
                        lines = get_logcat_capture().get_recent(max_lines=20)
                        if lines:
                            _cmd_logger.log_logcat_snapshot(f"loop_detected:{subgoal.description[:40]}", lines)
                    except Exception:
                        pass

                    # If the current subgoal already has goal_complete / phase_complete
                    # set (e.g. a follow-up `wait` after confirming playback), the screen
                    # not changing is EXPECTED — do not trigger stuck-recovery.
                    if subgoal.parameters.get("__goal_complete__") or subgoal.parameters.get("__phase_complete__"):
                        logger.info(
                            "Coordinator: loop on goal/phase-complete subgoal — "
                            "screen unchanged is expected, skipping recovery"
                        )
                        screen_hash_history.clear()
                        goal.advance_subgoal()
                        self._broadcast_step(session_id, success=True)
                        continue

                    # If we looped on a tap while the keyboard was already visible,
                    # the target field was already focused — advance as success.
                    if action_type == "tap" and "keyboard: visible" in (running_screen_context or "").lower():
                        logger.info(
                            f"Coordinator: tap on already-focused field detected — "
                            f"advancing '{subgoal.description[:50]}'"
                        )
                        screen_hash_history.clear()
                        goal.advance_subgoal()
                        self._broadcast_step(session_id, success=True)
                        continue

                    if recovery_injection_count >= 2:
                        goal.aborted = True
                        goal.abort_reason = "Stuck in same-screen loop (recovery exhausted)"
                        break

                    # --- Stuck-screen recovery injection ---
                    recovery_injection_count += 1
                    screen_hash_history.clear()

                    # Build rich obstacle for the planner
                    visible_labels = []
                    desc_text = None
                    if screen_state is not None:
                        for el in (screen_state.elements or [])[:20]:
                            label = (el.get("text") or "").strip() or (el.get("contentDescription") or "").strip()
                            if label:
                                visible_labels.append(label)
                        desc_text = screen_state.screen_description

                    obstacle = (
                        f"Screen unchanged after 3 attempts on subgoal '{subgoal.description}'. "
                        f"Visible elements: {visible_labels[:20]}. "
                        f"VLM description: {desc_text or 'not available'}. "
                        f"Running screen context: {running_screen_context or 'not available'}"
                    )

                    recovery_subgoals = self.planner.replan(
                        goal, obstacle,
                        perception=screen_state.perception_bundle if screen_state else None,
                        step_history=step_memory,
                    )[:2]
                    self._apply_replan(goal, recovery_subgoals)
                    _cmd_logger.log_agent_decision("STUCK_RECOVERY", {
                        "obstacle": obstacle[:120],
                        "recovery_injection_count": recovery_injection_count,
                        "injected_steps": [s.description for s in recovery_subgoals],
                    }, agent_name="Planner")
                    self._broadcast_start(session_id, goal)
                    continue

            if self.verifier.is_error_screen(post_elements):
                # Try going back from error screen
                _cmd_logger.log_agent_decision("ERROR_SCREEN_DETECTED", {
                    "subgoal": subgoal.description,
                    "action_type": action_type,
                    "recovery": "go_back",
                }, agent_name="Verifier")
                await self.actor.execute("go_back", parameters={})
                total_actions += 1
                subgoal.attempts += 1
                continue

            # --- Heuristic goal completion (deterministic, no VLM needed) ---
            # Fast-path: check the post-action UI tree for strong completion
            # signals (Pause button for music, active navigation view, etc.)
            # before spending a VLM call on the reactive step generator.
            _heuristic_complete, _heuristic_reason = _detect_goal_completion(
                goal.original_utterance, post_elements,
                pre_elements=screen_state.elements if screen_state else None,
            )
            if _heuristic_complete and action_result.success:
                logger.info(f"Coordinator: heuristic goal completion — {_heuristic_reason}")
                _cmd_logger.log_agent_decision("GOAL_COMPLETE_HEURISTIC", {
                    "subgoal": subgoal.description,
                    "reason": _heuristic_reason,
                    "goal": goal.original_utterance[:80],
                }, agent_name="Coordinator")
                step_memory.append(StepMemory(
                    subgoal_description=subgoal.description,
                    action_type=action_type,
                    target=subgoal.target,
                    result="success",
                    screen_type=screen_state.screen_type if screen_state else "unknown",
                    screen_before=pre_signature,
                    screen_after=post_signature,
                    coordinates=coordinates,
                    key_state_after=_heuristic_reason,
                ))
                goal.advance_subgoal()
                while goal.current_phase:
                    goal.advance_phase()
                goal.completed = True
                self._broadcast_step(session_id, success=True)
                break

            # --- Merged verification + next-step generation (one VLM call) ---
            _post_b64 = ""
            if post_bundle and post_bundle.screenshot and post_bundle.screenshot.screenshot_base64:
                _post_b64 = post_bundle.screenshot.screenshot_base64
                if _post_b64 and post_elements:
                    try:
                        _sw = getattr(post_bundle.screen_meta, "width", 1080) or 1080
                        _sh_px = getattr(post_bundle.screen_meta, "height", 1920) or 1920
                        _post_b64, _filtered_post = self.perceiver.build_annotated_screenshot(_post_b64, post_elements, _sw, _sh_px)
                        if _filtered_post:
                            post_elements = _filtered_post
                    except Exception:
                        pass

            next_step = None
            verification_passed = True
            verification_reason = "action succeeded"
            if self.reactive_gen:
                self.task_progress.emit_agent_status("Reactive", "Verifying + next step")
                next_step = self.reactive_gen.generate_next_step(
                    goal, running_screen_context, step_memory,
                    screenshot_b64=_post_b64, ui_hints="",
                    ui_elements=post_elements,
                    prev_subgoal=subgoal,
                    prev_action_succeeded=action_result.success,
                )
            if next_step:
                verification_passed = next_step.parameters.pop("__verification_passed__", True)
                verification_reason = next_step.parameters.pop("__verification_reason__", "VLM confirmed")
                _reactive_ctx = next_step.parameters.get("__screen_context__", "")
                if _reactive_ctx:
                    running_screen_context = str(_reactive_ctx)[:800]
            elif not action_result.success:
                verification_passed = False
                verification_reason = f"Action execution failed: {action_result.error}"

            if verification_passed:
                # AI-writer escape: if we just tapped a compose-area target and the
                # post-action screen now shows Gmail's "Help me write" AI overlay
                # (signalled by a clickable "Create" button with no "Send"), press
                # Back and retry this subgoal so the agent lands in the real body.
                if action_type == "tap" and subgoal.target and any(
                    kw in subgoal.target.lower()
                    for kw in ("body", "message body", "compose", "help me write")
                ):
                    ai_overlay = any(
                        (e.get("text") or "").lower() == "create" and e.get("clickable", False)
                        for e in post_elements
                    )
                    if ai_overlay:
                        logger.warning(
                            f"Coordinator: AI writer overlay detected after tapping "
                            f"'{subgoal.target}' — pressing Back to dismiss"
                        )
                        await self.actor.execute("go_back", parameters={})
                        total_actions += 1
                        subgoal.attempts += 1
                        continue  # retry the tap subgoal

                # --- Goal-complete target verification ---
                # Before accepting phase_complete / goal_complete, verify that the
                # element actually tapped matches the intended target text.
                # This catches false completions (e.g., tapping "All Filters" when
                # instructed to tap "Add to cart").
                if (
                    subgoal.parameters.get("__phase_complete__")
                    and action_type == "tap"
                    and subgoal.target
                    and coordinates
                ):
                    _target_verified = False
                    _tapped_label = ""
                    # Check the pre-action UI tree for the element at tapped coordinates
                    _verify_elements = []
                    if screen_state and screen_state.elements:
                        _verify_elements = screen_state.elements
                    elif post_elements:
                        _verify_elements = post_elements

                    _target_lower = subgoal.target.lower()
                    for _el in _verify_elements:
                        _b = _el.get("bounds") or _el.get("visibleBounds") or _el.get("boundsInScreen") or {}
                        _l, _r = _b.get("left", 0), _b.get("right", 0)
                        _t, _tp = _b.get("top", 0), _b.get("bottom", 0)
                        # Check if tapped coordinates fall within this element's bounds
                        if _l <= coordinates[0] <= _r and _t <= coordinates[1] <= _tp:
                            _txt = (_el.get("text") or "").strip()
                            _desc = (_el.get("contentDescription") or "").strip()
                            _tapped_label = _txt or _desc
                            # Verify: target text should appear in element text/desc
                            if (_target_lower in _txt.lower() or _target_lower in _desc.lower()
                                    or _txt.lower() in _target_lower or _desc.lower() in _target_lower):
                                _target_verified = True
                            break

                    if not _target_verified and _tapped_label:
                        logger.warning(
                            f"Coordinator: goal_complete verification FAILED — "
                            f"target='{subgoal.target}' but tapped element='{_tapped_label}'"
                        )
                        _cmd_logger.log_agent_decision("GOAL_COMPLETE_MISMATCH", {
                            "subgoal": subgoal.description,
                            "expected_target": subgoal.target,
                            "tapped_element": _tapped_label,
                            "coordinates": list(coordinates),
                        }, agent_name="Coordinator")
                        # Do NOT accept phase_complete — retry with scroll to find the real target
                        subgoal.parameters.pop("__phase_complete__", None)
                        await self.actor.execute("scroll", parameters={"direction": "down"})
                        total_actions += 1
                        subgoal.attempts += 1
                        continue

                logger.info(f"Coordinator: subgoal verified — {subgoal.description}")

                _cmd_logger.log_agent_decision("SUBGOAL_COMPLETE", {
                    "subgoal": subgoal.description,
                    "action_type": action_type,
                    "screen_changed": screen_changed,
                    "screen_before": pre_signature[:16],
                    "screen_after": post_signature[:16],
                    "verification_reason": verification_reason,
                }, agent_name="Verifier")
                step_memory.append(StepMemory(
                    subgoal_description=subgoal.description,
                    action_type=action_type,
                    target=subgoal.target,
                    result="success",
                    screen_type=screen_state.screen_type if screen_state else "unknown",
                    screen_before=pre_signature,
                    screen_after=post_signature,
                    coordinates=coordinates,
                    screen_description=screen_state.screen_description if screen_state else None,
                    key_state_after=_media_state_summary(post_elements) or None,
                ))
                if next_step:
                    goal.subgoals.append(next_step)
                goal.advance_subgoal()
                if subgoal.parameters.get("__phase_complete__") and goal.phases:
                    _prev = goal.current_phase.description if goal.current_phase else "?"
                    goal.advance_phase()
                    logger.info(f"Coordinator: phase complete → {goal.current_phase.description if goal.current_phase else 'all done'}")
                    _cmd_logger.log_agent_decision("PHASE_COMPLETE", {
                        "signal": "step_flag",
                        "completed_phase": _prev,
                        "next_phase": goal.current_phase.description if goal.current_phase else None,
                    }, agent_name="Coordinator")
                self._broadcast_step(session_id, success=True)
            else:
                # W10 fix: use retry ladder before replan
                subgoal.attempts += 1
                strategy = subgoal.escalate_strategy()
                logger.info(f"Coordinator: retrying with strategy {strategy.value} (attempt {subgoal.attempts})")
                _cmd_logger.log_agent_decision("VERIFICATION_FAILED", {
                    "subgoal": subgoal.description,
                    "action_type": action_type,
                    "reason": verification_reason,
                    "screen_changed": screen_changed,
                    "attempt": subgoal.attempts,
                    "retry_strategy": strategy.value,
                }, agent_name="Verifier")

                if strategy == RetryStrategy.ABORT:
                    # Exhausted retry ladder — replan
                    replan_count += 1
                    if replan_count > MAX_REPLAN_ATTEMPTS:
                        goal.aborted = True
                        goal.abort_reason = "Max replan attempts exceeded"
                        break
                    screen_hash_history.clear()
                    obstacle = f"Subgoal '{subgoal.description}' failed after {subgoal.attempts} attempts: {verification_reason}"
                    new_subgoals = self.planner.replan(
                        goal, obstacle,
                        perception=post_bundle,
                        step_history=step_memory,
                    )
                    self._apply_replan(goal, new_subgoals)
                    _cmd_logger.log_agent_decision("REPLAN", {
                        "reason": "verification_failed",
                        "obstacle": obstacle,
                        "replan_count": replan_count,
                        "new_subgoal_count": len(new_subgoals),
                    }, agent_name="Planner")
                    self._broadcast_start(session_id, goal)
                # Other strategies: loop back to perceive with appropriate flags
                # SAME_ACTION / ALTERNATE_SELECTOR / SCROLL_AND_RETRY / VISION_FALLBACK
                # are handled by the continue — perceive runs again next iteration

        # --- Build result ---
        status = "completed" if goal.completed else "aborted"
        error = goal.abort_reason if goal.aborted else None

        # Restore normal keyboard behaviour now that automation is done so the
        # user can type freely in other apps.
        try:
            await self.actor.execute("restore_keyboard", parameters={})
        except Exception:
            pass  # best-effort; don't fail the task over this

        return {
            "status": status,
            "goal": goal,
            "executed_steps": executed_steps,
            "step_memory": step_memory,
            "total_actions": total_actions,
            "error": error,
        }

    def _extract_cart_count(self, screen_state: "ScreenState") -> Optional[int]:
        """
        Extract cart/bag item count from a screen badge or counter element.

        Looks for a digit-only text element whose content-description mentions
        cart, bag, or basket.  Returns None when no badge is found.
        """
        for el in (screen_state.elements or []):
            text = (el.get("text") or "").strip()
            desc = (el.get("contentDescription") or "").strip().lower()
            if text.isdigit() and any(kw in desc for kw in ("cart", "bag", "basket")):
                return int(text)
        return None

    def _find_search_submit_coords(self, elements: List[Dict]) -> Optional[Tuple[int, int]]:
        """
        Find the coordinates of a search/submit button in the current UI elements.

        Used as a fallback when press_enter has no effect — some apps (e.g. Amazon)
        require tapping their custom search button rather than IME key events.
        """
        search_keywords = {"search", "submit", "go", "find"}
        for el in elements or []:
            text = (el.get("text") or "").lower()
            desc = (el.get("contentDescription") or "").lower()
            if any(kw in text or kw in desc for kw in search_keywords):
                bounds = (
                    el.get("bounds")
                    or el.get("visibleBounds")
                    or el.get("boundsInScreen")
                )
                if bounds:
                    x = (bounds.get("left", 0) + bounds.get("right", 0)) // 2
                    y = (bounds.get("top", 0) + bounds.get("bottom", 0)) // 2
                    if x > 0 or y > 0:
                        return (x, y)
        return None

    @staticmethod
    def _extract_open_app_phase(phase_desc: str) -> Optional[str]:
        """Return the app name if the phase is just 'Open <App>', else None."""
        import re
        m = re.match(r"^(?:Open|Launch|Start)\s+(.+)$", phase_desc, re.IGNORECASE)
        if not m:
            return None
        app_name = m.group(1).strip()
        # Reject if it looks like a deeper navigation goal, not a simple app open
        if any(kw in app_name.lower() for kw in [" and ", " then ", " to ", "'s ", " in ", " on "]):
            return None
        return app_name

    @staticmethod
    def _find_input_field_name(screen_context: str) -> Optional[str]:
        """Extract the first input field name from screen context (e.g. 'Search bar')."""
        import re
        # Match "INPUT FIELDS:" section entries like "- Search bar: empty"
        match = re.search(
            r"INPUT FIELDS:\s*\n?\s*-\s*(.+?)(?::\s|\n|$)",
            screen_context,
        )
        if match:
            return match.group(1).strip()
        # Fallback: look for common patterns like "Search bar: ..."
        match = re.search(r"(Search bar|Search field|Search|Text field)", screen_context, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None

    # Known input className substrings — covers standard Android views, React Native,
    # Flutter (via semantics bridge), common custom views across popular apps.
    _INPUT_CLASS_KEYWORDS = (
        "edittext", "textinput", "autocomplete", "multiautocomplete",
        "recipient", "searchview", "searchedittext", "searchbar",
        "pinview", "otpview", "codeview", "codeinput", "codeentry",
        "passwordinput", "passwordview", "amountinput", "phoneinput",
        "emailinput", "textfield", "clearableedittext", "floatinglabel",
    )

    # Ordinal positions for well-known form patterns.
    # Negative indices work like Python list[-1] (last field, second-to-last, etc.)
    _FIELD_ORDINALS: dict = {
        # Email compose
        "to": 0, "recipient": 0,
        "cc": 1, "bcc": 2,
        "subject": -2,
        "message": -1, "body": -1, "compose": -1, "compose email": -1,
        # Login
        "username": 0, "user name": 0,
        "email": 0, "email address": 0,
        "password": -1, "passcode": -1, "pin": -1,
        # Sign-up
        "name": 0, "full name": 0, "first name": 0,
        "last name": 1,
        "phone": -1, "mobile": -1, "phone number": -1,
        # Search
        "search": 0, "query": 0,
    }

    @staticmethod
    def _is_input_element(el: dict) -> bool:
        """
        Returns True if this accessibility element is an interactive input field.
        Works across any Android app, framework, or custom View subclass.
        """
        if el.get("editable") or el.get("isEditable"):
            return True
        # inputType is set and non-zero/non-null means the OS treats it as a text input
        input_type = el.get("inputType")
        if input_type and input_type not in (0, "0", "none", "TYPE_NULL", "TYPE_CLASS_NULL"):
            return True
        cls = (el.get("className") or "").lower()
        return any(kw in cls for kw in Coordinator._INPUT_CLASS_KEYWORDS)

    @staticmethod
    def _match_intended_edit_field(
        field_hint: str,
        description: str,
        edit_elements: List[Dict],
        all_elements: Optional[List[Dict]] = None,
    ) -> Optional[Dict]:
        """
        Production-grade field matching using 5 signal layers.

        Layer 1 — Exact identity: hint/hintText/contentDescription equals field_hint
        Layer 2 — Whole-word boundary match in any signal string
        Layer 3 — Label proximity: find a non-editable label whose text ==
                   field_hint, then return the input element spatially closest below it
        Layer 4 — Token scoring across all word tokens from field_hint + description
        Layer 5 — Ordinal fallback for well-known form field orderings

        Returns the best-matching element, or None.
        """
        if not edit_elements:
            return None

        import re as _re

        hint_norm = field_hint.strip().lower()

        def _signals(el: Dict) -> str:
            return " ".join(filter(None, [
                (el.get("hint") or el.get("hintText") or "").lower(),
                (el.get("contentDescription") or "").lower(),
                (el.get("resourceId") or "").lower().replace("_", " ").replace("/", " ").replace(":", " "),
                (el.get("text") or "").lower(),
            ]))

        # Layer 1: exact match on hint or contentDescription
        if hint_norm:
            for el in edit_elements:
                el_hint = (el.get("hint") or el.get("hintText") or "").lower().strip()
                el_desc = (el.get("contentDescription") or "").lower().strip()
                if el_hint == hint_norm or el_desc == hint_norm:
                    return el

        # Layer 2: whole-word boundary match in combined signals
        if hint_norm:
            pattern = _re.compile(r"\b" + _re.escape(hint_norm) + r"\b")
            candidates = [el for el in edit_elements if pattern.search(_signals(el))]
            if len(candidates) == 1:
                return candidates[0]
            if len(candidates) > 1:
                # tiebreak: prefer the field with least existing text (likely empty/target)
                return min(candidates, key=lambda e: len(e.get("text") or ""))

        # Layer 3: label proximity
        # Find a non-editable element acting as a field label whose text matches
        # field_hint, then return the input closest spatially below/right of it.
        if hint_norm and all_elements:
            label_el = None
            for el in all_elements:
                if not Coordinator._is_input_element(el):
                    el_text = (el.get("text") or "").lower().strip()
                    if el_text == hint_norm or el_text.startswith(hint_norm + " ") or el_text.startswith(hint_norm + ":"):
                        label_el = el
                        break
            if label_el:
                lb = label_el.get("bounds") or {}
                lx = (lb.get("left", 0) + lb.get("right", 0)) / 2
                ly = (lb.get("top", 0) + lb.get("bottom", 0)) / 2

                def _proximity(el: Dict) -> float:
                    eb = el.get("bounds") or {}
                    ex = (eb.get("left", 0) + eb.get("right", 0)) / 2
                    ey = (eb.get("top", 0) + eb.get("bottom", 0)) / 2
                    dy = ey - ly
                    dx = abs(ex - lx)
                    # Penalise fields that are above the label (likely a different row)
                    if dy < -30:
                        return float("inf")
                    return dy + dx * 0.4

                closest = min(edit_elements, key=_proximity)
                if _proximity(closest) < 600:
                    return closest

        # Layer 4: token scoring — every word ≥ 2 chars from hint + description
        combined = (field_hint + " " + description).lower()
        tokens = [t for t in _re.findall(r"\b\w{2,}\b", combined) if t not in ("to", "in", "an", "of", "the", "and", "for")]
        # also always include the raw hint_norm tokens even if short
        if hint_norm:
            tokens.extend(hint_norm.split())
        if tokens:
            best_el, best_score = None, 0
            for el in edit_elements:
                sig = _signals(el)
                score = sum(1 for tok in tokens if tok in sig)
                if score > best_score:
                    best_score, best_el = score, el
            if best_el and best_score > 0:
                return best_el

        # Layer 5: ordinal fallback for well-known field sequences
        ordinals = Coordinator._FIELD_ORDINALS
        idx = ordinals.get(hint_norm)
        if idx is not None:
            try:
                return edit_elements[idx]
            except IndexError:
                pass

        return None

    async def _handle_target_not_found(
        self,
        subgoal: "Subgoal",
        intent: Dict[str, Any],
        screen_state: "ScreenState",
        goal: Goal,
        executed_steps: List[Dict],
        total_actions: int,
        screen_hash_history: List[str],
        step_memory: Optional[List] = None,
    ) -> str:
        """
        Handle case where target element is not found on screen.

        Uses retry ladder: scroll → force VLM → replan.

        Returns:
            "found" if target located after retry,
            "replan" if should replan,
            "abort" if should abort.
        """
        strategy = subgoal.current_strategy
        _utterance = goal.original_utterance
        _plan_context = "\n".join(
            f"{i+1}. [{sg.action_type}] {sg.description} → {sg.target or '-'}"
            for i, sg in enumerate(goal.subgoals)
        )

        # Try scrolling to find it
        if subgoal.attempts == 0:
            subgoal.attempts += 1
            subgoal.escalate_strategy()
            logger.info("Coordinator: target not found — scrolling down to search")
            await self.actor.execute("scroll", parameters={"direction": "down"})
            new_screen = await self.perceiver.perceive(
                subgoal, intent, step_history=step_memory,
                user_command=_utterance, plan_context=_plan_context,
            )
            if new_screen.target_match:
                return "found"

        # Try force VLM perception
        if subgoal.attempts <= 2:
            subgoal.attempts += 1
            subgoal.escalate_strategy()
            logger.info("Coordinator: target not found — forcing VLM perception")
            new_screen = await self.perceiver.perceive(
                subgoal, intent, force_screenshot=True, step_history=step_memory,
                user_command=_utterance, plan_context=_plan_context,
            )
            if new_screen.target_match:
                return "found"

        return "replan"

    async def _snapshot_pre(self, intent: Dict[str, Any]) -> str:
        """
        Capture a fresh UI signature right before action execution.

        This is separate from perceive — it captures the true pre-action
        state for accurate verification (W1 fix).
        """
        bundle = await self.perceiver.perception_controller.request_perception(
            intent=intent,
            action_type="verify",
            force_screenshot=False,
        )
        elements = []
        if bundle.ui_tree and hasattr(bundle.ui_tree, "elements"):
            elements = bundle.ui_tree.elements or []
        return compute_ui_signature(elements)

    def _apply_replan(self, goal: Goal, new_subgoals: List["Subgoal"]) -> None:
        """Replace remaining subgoals with new plan from replanner."""
        # Keep completed subgoals, replace the rest
        completed = [sg for sg in goal.subgoals if sg.completed]
        goal.subgoals = completed + new_subgoals
        goal.current_subgoal_index = len(completed)
        goal.completed = False
        goal.aborted = False
        goal.abort_reason = None
        logger.info(f"Coordinator: replan applied — {len(new_subgoals)} new subgoals")

    def _broadcast_start(self, session_id: str, goal: Goal) -> None:
        """Broadcast task start to WebSocket clients."""
        try:
            if goal.phases:
                subgoal_dicts = [
                    {"description": p.description, "action_type": "phase"}
                    for p in goal.phases
                ]
            else:
                subgoal_dicts = [
                    {"description": sg.description, "action_type": sg.action_type}
                    for sg in goal.subgoals
                ]
            self.task_progress.start_task(session_id, goal.description, subgoal_dicts)
        except Exception as e:
            logger.debug(f"Broadcast start failed: {e}")

    def _broadcast_step(self, session_id: str, success: bool) -> None:
        """Broadcast step completion to WebSocket clients."""
        try:
            self.task_progress.complete_current_step(session_id, success)
        except Exception as e:
            logger.debug(f"Broadcast step failed: {e}")
