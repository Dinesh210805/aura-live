"""
Reactive step generator — layer 2 of the hybrid planner.

Produces ONE concrete next action grounded in the live screen state.
Called by the Coordinator at each loop iteration when no pending subgoal
exists, replacing the upfront full-plan-commitment with a per-screen decision.
"""

import asyncio
import json
import re
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import List, Optional

from aura_graph.agent_state import Goal, Phase, StepMemory, Subgoal
from config.success_criteria import get_success_criteria
from prompts.reactive_step import get_reactive_step_messages, get_reactive_step_prompt
from services.llm import LLMService
from utils.logger import get_logger

logger = get_logger(__name__)

# Stored in Subgoal.parameters to signal the coordinator to advance the phase
# after executing this step.
PHASE_COMPLETE_KEY = "__phase_complete__"

# FIXED: FIX-002 — bounded executor prevents unbounded thread spawning
_LLM_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="llm_worker")


def _is_commit_satisfied(commit: str, target: str) -> bool:
    """
    Check if a pending commit is satisfied by a target action.
    Uses exact match or normalized equivalence (underscore↔space).

    # FIXED: FIX-011 — previous substring match caused false positives
    # e.g., "send" would incorrectly match "send_button"
    """
    commit_norm = commit.lower().strip().replace("_", " ")
    target_norm = target.lower().strip().replace("_", " ")
    return commit_norm == target_norm


class ReactiveStepGenerator:
    """
    Generates one concrete next UI action grounded in the current screen.

    Called at each coordinator loop iteration when no pending subgoal exists.
    Uses the same planning LLM provider to decide: given (goal, current phase,
    live screen elements, step history) → what is the single next tap/type/etc.
    """

    def __init__(self, llm_service: LLMService, vlm_service=None):
        self.llm_service = llm_service
        self.vlm_service = vlm_service  # Optional — used when screen_context is degraded

    async def generate_next_step(
        self,
        goal: Goal,
        screen_context: str,
        step_history: List[StepMemory],
        screenshot_b64: str = "",
        ui_hints: str = "",
        ui_elements=None,
        prev_subgoal: Optional[Subgoal] = None,
        prev_action_succeeded: bool = True,
    ) -> Optional[Subgoal]:
        """
        Generate the next concrete step for the current phase.

        Returns:
            A ready-to-execute Subgoal, or None when the current phase is
            complete (signals the coordinator to call goal.advance_phase()).

        # FIXED: FIX-002 — now async; LLM/VLM calls dispatched to bounded thread executor
        """
        if not goal.current_phase:
            return None

        # Deterministic pre-VLM override: after typing into a recipient/contact field,
        # detect any visible autocomplete suggestion and tap it immediately —
        # prevents VLM blindness when Gmail auto-focuses the body while the
        # suggestion dropdown is still present.
        autocomplete_subgoal = self._detect_autocomplete_suggestion(prev_subgoal, ui_elements)
        if autocomplete_subgoal is not None:
            return autocomplete_subgoal

        # Build previous action descriptor for VLM verification
        if prev_subgoal is not None:
            _prev_act_desc = prev_subgoal.target or (
                prev_subgoal.description[:50] if prev_subgoal.description else "unknown"
            )
            prev_action = (
                f"[{prev_subgoal.action_type}] {_prev_act_desc} "
                f"| gesture_ok: {str(prev_action_succeeded).lower()}"
            )
        else:
            prev_action = "None (first step)"

        # FIXED: FIX-013 — compress history for long tasks
        from config.settings import get_settings
        settings_obj = get_settings()
        history_summary, recent_steps = await self._get_compressed_history(
            step_history, window_size=settings_obj.step_history_window
        )
        steps_done_str = self._format_history(recent_steps)
        if history_summary:
            steps_done_str = f"{history_summary}\n\nRecent steps:\n{steps_done_str}"

        _prompt_kwargs = dict(
            goal=goal.original_utterance,
            phase=goal.current_phase.description,
            screen_context=screen_context,
            steps_done=steps_done_str,
            pending_commits=", ".join(goal.pending_commits) if goal.pending_commits else "None",
            last_failure=self._last_failure_reason(step_history),
            ui_hints=ui_hints,
            ui_elements=self._format_elements(ui_elements),
            prev_action=prev_action,
        )

        # FIXED: FIX-014 — inject reflexion lesson from previous failed attempt if available
        reflexion_lesson = ""
        try:
            from services.reflexion_service import get_reflexion_service
            reflexion = get_reflexion_service()
            if reflexion and goal.original_utterance:
                lessons = await reflexion.get_lessons_for_goal(goal.original_utterance, max_lessons=1)
                reflexion_lesson = lessons[0] if lessons else ""
        except Exception:
            pass  # Reflexion is best-effort, never block execution

        try:
            # Use VLM whenever a screenshot is available — the model sees the
            # actual screen + goal context in a single call, eliminating the
            # separate describe_screen → text-only-LLM round-trip.
            use_vision = bool(screenshot_b64 and self.vlm_service)

            if use_vision:
                # System/user split: static rules cached by Groq at 50% token cost.
                sys_msg, user_msg = get_reactive_step_messages(**_prompt_kwargs)
                if reflexion_lesson:
                    user_msg = f"\n⚠️ LESSON FROM PREVIOUS ATTEMPT:\n{reflexion_lesson}\n\n{user_msg}"
                logger.info("ReactiveStepGenerator: VLM call (system/user split, cached rules)")
                raw = await asyncio.get_event_loop().run_in_executor(
                    _LLM_EXECUTOR,
                    partial(
                        self.vlm_service.analyze_image,
                        screenshot_b64,
                        user_msg,
                        system_prompt=sys_msg,
                        agent="ReactiveStepGen",
                        temperature=0.2,
                    )
                )
            else:
                prompt = get_reactive_step_prompt(**_prompt_kwargs)
                if reflexion_lesson:
                    prompt = f"\n⚠️ LESSON FROM PREVIOUS ATTEMPT:\n{reflexion_lesson}\n\n{prompt}"
                settings = self.llm_service.settings
                raw = await asyncio.get_event_loop().run_in_executor(
                    _LLM_EXECUTOR,
                    partial(
                        self.llm_service.run,
                        prompt,
                        max_tokens=800,
                        provider=settings.planning_provider,
                        model=settings.planning_model,
                        response_format={"type": "json_object"},
                        temperature=0.1,
                    )
                )
            parsed = self._parse_json(raw)
            if not parsed:
                logger.warning("ReactiveStepGenerator: LLM returned unparseable response")
                return None

            action_type = parsed.get("action_type", "tap")
            target = parsed.get("target")
            field_hint = (parsed.get("field_hint") or "").strip()
            description = parsed.get("description") or f"[{action_type}] {target or ''}"
            phase_complete = bool(parsed.get("phase_complete", False))
            goal_complete = bool(parsed.get("goal_complete", False))
            returned_screen_context = parsed.get("screen_context", "")
            prev_step_ok = bool(parsed.get("prev_step_ok", True))
            prev_step_issue = (parsed.get("prev_step_issue") or "").strip()
            thinking = (parsed.get("thinking") or "").strip()
            evaluation = (parsed.get("evaluation") or "").strip()
            memory = (parsed.get("memory") or "").strip()
            if thinking:
                logger.info(f"🧠 Thinking: {thinking[:200]}")
            if evaluation:
                logger.info(f"📋 Evaluation: {evaluation[:200]}")
            if memory:
                logger.info(f"🗂️ Memory: {memory[:200]}")

            # v4 prompt removed prev_step_ok/prev_step_issue in favour of
            # verification_passed/verification_reason. Support both forms.
            verification_passed = bool(parsed.get("verification_passed", prev_step_ok))
            verification_reason = (
                parsed.get("verification_reason")
                or parsed.get("evaluation")
                or prev_step_issue
                or ""
            ).strip()
            # If prev_step_ok=false but no verification_passed key → treat as failed
            if not prev_step_ok and "verification_passed" not in parsed:
                verification_passed = False
            if not prev_step_issue and not parsed.get("verification_reason"):
                prev_step_issue = verification_reason
            if prev_subgoal is None:
                verification_passed = True
                verification_reason = "first step"

            # Tick off any pending commit that this step fulfils
            if target and goal.pending_commits:
                goal.pending_commits = [
                    c for c in goal.pending_commits
                    if not _is_commit_satisfied(c, target)
                    # FIXED: FIX-011 — was substring match, now exact/normalized match
                ]

            # Fast-path: LLM says the entire goal is done after this step
            if goal_complete:
                while goal.current_phase:
                    goal.advance_phase()

            criteria = get_success_criteria(action_type)
            if action_type == "open_app" and target and criteria.target_screen_reached is not None:
                criteria.target_screen_reached = target.lower()

            subgoal = Subgoal(
                description=description,
                action_type=action_type,
                target=target,
                success_criteria=criteria,
            )
            if phase_complete:
                subgoal.parameters[PHASE_COMPLETE_KEY] = True
            if returned_screen_context:
                subgoal.parameters["__screen_context__"] = returned_screen_context
            if field_hint:
                subgoal.parameters["__field_hint__"] = field_hint
            if not prev_step_ok and prev_step_issue:
                subgoal.parameters["__prev_step_ok__"] = False
                subgoal.parameters["__prev_step_issue__"] = prev_step_issue
                logger.warning(
                    f"ReactiveStepGenerator: prev step issue detected — {prev_step_issue[:100]}"
                )

            subgoal.parameters["__verification_passed__"] = verification_passed
            if verification_reason:
                subgoal.parameters["__verification_reason__"] = verification_reason

            logger.info(
                f"🦭 Reactive step [{action_type}] {target!r} "
                f"(phase_complete={phase_complete}, goal_complete={goal_complete}, "
                f"verification_passed={verification_passed})"
            )
            return subgoal

        except Exception as e:
            logger.error(f"ReactiveStepGenerator.generate_next_step failed: {e}")
            return None

    def _format_elements(self, elements) -> str:
        """Format UI elements list into a rich reference string for the prompt."""
        from utils.ui_element_finder import format_ui_tree
        return format_ui_tree(elements)

    def _format_history(self, step_history: List[StepMemory]) -> str:
        if not step_history:
            return "None yet"
        parts = []
        for m in step_history:
            icon = "✅" if m.result == "success" else "❌"
            # For type actions, show the description (which carries the field name)
            if m.action_type in ("type", "type_text", "enter_text", "set_text", "input_text"):
                label = m.subgoal_description[:80] if m.subgoal_description else f"type({m.target or ''})"
                entry = f"{icon} {label}"
            else:
                entry = f"{icon} {m.action_type}({m.target or ''}) → {m.screen_type}"
            if m.result != "success" and m.screen_description:
                screen_note = m.screen_description[:80].replace("\n", " ")
                entry += f" [screen: {screen_note}]"
            # Append post-action state delta for the next turn's ① VERIFY PREV check
            if m.key_state_after:
                entry += f" [→ {m.key_state_after}]"
            parts.append(entry)
        return " → ".join(parts)

    def _last_failure_reason(self, step_history: List[StepMemory]) -> str:
        for m in reversed(step_history):
            if m.result != "success":
                note = f"[{m.action_type}] {m.subgoal_description[:60]}"
                if m.screen_description:
                    note += f" — screen: {m.screen_description[:80].replace(chr(10), ' ')}"
                return note
        return ""

    async def _get_compressed_history(
        self,
        step_history: list,
        window_size: int = 6
    ) -> tuple:
        """
        Compress step history for long tasks.

        Returns (summary_string, recent_steps) where summary covers steps
        older than window_size. If history fits in window, returns ("", all_steps).

        # FIXED: FIX-013 — previous hard cutoff [-6:] lost early task context
        # for long tasks, causing re-navigation of already-visited screens.
        """
        if len(step_history) <= window_size:
            return "", step_history

        old_steps = step_history[:-window_size]
        recent_steps = step_history[-window_size:]

        step_lines = "\n".join(
            f"  {i+1}. [{m.action_type}] {m.target or m.subgoal_description[:40]} → {m.result}"
            for i, m in enumerate(old_steps)
        )
        summary_prompt = (
            f"Summarize what the agent has done so far in 2-3 sentences. "
            f"Focus on: what screens visited, what actions succeeded, what fields filled. "
            f"Be specific and concise.\n\nSteps:\n{step_lines}"
        )

        try:
            loop = asyncio.get_event_loop()
            summary = await loop.run_in_executor(
                _LLM_EXECUTOR,
                partial(self.llm_service.run, summary_prompt)
            )
            logger.debug(f"Compressed {len(old_steps)} old steps into summary ({len(summary)} chars)")
            return f"[Prior steps summary]: {summary}", recent_steps
        except Exception as e:
            logger.warning(f"History compression failed, using truncated history: {e}")
            return "", recent_steps

    def _parse_json(self, text: Optional[str]) -> Optional[dict]:
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except Exception:
                    pass
        return None
