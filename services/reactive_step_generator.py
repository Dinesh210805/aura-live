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
        screen_width: int = 1080,
        screen_height: int = 1920,
        agent_memory: str = "",
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
            agent_memory=agent_memory,
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

            # ── SoM coordinate resolution ──────────────────────────────────────
            # Extract new schema gesture fields and resolve element_id / from_element
            # references to concrete pixel coordinates BEFORE building the Subgoal.
            # Backward-compatible: if these keys are absent the block is a no-op.
            _gesture      = parsed.get("gesture")
            _element_id   = parsed.get("element_id")
            _from_element = parsed.get("from_element")
            _to_element   = parsed.get("to_element")
            _direction    = (parsed.get("direction") or "").lower().strip()
            _distance_frac = float(parsed.get("distance_frac") or 0.5)
            _duration_ms  = parsed.get("duration_ms")
            _som_tap_coords = None          # (cx, cy) for tap / long_press
            _som_swipe_params: dict = {}    # start_x/y + end_x/y for swipe

            # "gesture" field (new schema) takes priority over legacy "action_type"
            if _gesture:
                parsed["action_type"] = _gesture

            if ui_elements and (_element_id is not None or _from_element is not None):
                from utils.ui_element_finder import get_element_center

                def _som_center(idx):
                    """1-indexed element_id → (cx, cy) or None."""
                    try:
                        i = int(idx)
                        if 1 <= i <= len(ui_elements):
                            return get_element_center(ui_elements[i - 1])
                    except (ValueError, TypeError):
                        pass
                    return None

                if _element_id is not None:
                    _c = _som_center(_element_id)
                    if _c:
                        _som_tap_coords = _c
                        logger.debug(f"SoM: element_id={_element_id} → coords={_c}")

                elif _from_element is not None:
                    _fc = _som_center(_from_element)
                    if _fc:
                        fx, fy = _fc
                        _tc = _som_center(_to_element) if _to_element is not None else None
                        if _tc:
                            tx, ty = _tc
                            _som_swipe_params = {
                                "start_x": fx, "start_y": fy,
                                "end_x": tx,   "end_y": ty,
                            }
                        elif _direction:
                            _dh = int(_distance_frac * screen_height)
                            _dw = int(_distance_frac * screen_width)
                            _dir_delta = {
                                "up":    (0, -_dh),
                                "down":  (0,  _dh),
                                "left":  (-_dw, 0),
                                "right": ( _dw, 0),
                            }
                            _dx, _dy = _dir_delta.get(_direction, (0, _dh))
                            _som_swipe_params = {
                                "start_x": fx,        "start_y": fy,
                                "end_x":   fx + _dx,  "end_y":   fy + _dy,
                            }
                        if _som_swipe_params and _duration_ms:
                            _som_swipe_params["duration"] = int(_duration_ms)
                        logger.debug(
                            f"SoM: from_element={_from_element}→{_fc} "
                            f"swipe_params={_som_swipe_params}"
                        )
            # Fallback: bare "swipe" + direction with no element anchoring.
            # The new schema puts direction in the "direction" field, not "target".
            # If SoM resolution produced no coords (no from_element), inject
            # screen-center-based start/end so the executor always gets valid coords.
            if (
                not _som_swipe_params
                and (_gesture == "swipe" or parsed.get("action_type") == "swipe")
                and _direction in ("up", "down", "left", "right")
            ):
                cx = screen_width // 2
                cy = screen_height // 2
                _frac = _distance_frac or 0.4
                _dh = int(_frac * screen_height)
                _dw = int(_frac * screen_width)
                _dir_delta = {
                    "up":    (0, -_dh),
                    "down":  (0,  _dh),
                    "left":  (-_dw, 0),
                    "right": ( _dw, 0),
                }
                _dx, _dy = _dir_delta[_direction]
                _som_swipe_params = {
                    "start_x": cx,        "start_y": cy,
                    "end_x":   cx + _dx,  "end_y":   cy + _dy,
                }
                if _duration_ms:
                    _som_swipe_params["duration"] = int(_duration_ms)
                logger.debug(
                    f"SoM: bare-direction swipe {_direction!r} frac={_frac} → "
                    f"({cx},{cy})→({cx+_dx},{cy+_dy})"
                )
            # ──────────────────────────────────────────────────────────────────

            action_type = parsed.get("action_type", "tap")
            target = parsed.get("target")
            field_hint = (parsed.get("field_hint") or "").strip()
            description = parsed.get("description") or f"[{action_type}] {target or ''}"
            phase_complete = bool(parsed.get("phase_complete", False))
            goal_complete = bool(parsed.get("goal_complete", False))
            # Options for ask_user: list of visible on-screen choices the LLM extracted
            ask_user_options: list[str] = [
                str(o).strip() for o in (parsed.get("options") or [])
                if str(o).strip()
            ]

            # Deterministic post-parse override: if the LLM misses an obvious
            # completion signal in the screen (e.g. navigation already active),
            # detect it here so the loop terminates rather than spinning forever.
            if not goal_complete:
                goal_complete = self._detect_goal_achieved_from_screen(
                    screen_context, goal.original_utterance
                )

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

            # Generic guard (app-agnostic): after typing into a searchable picker,
            # do not advance with proceed buttons (Next/OK/Done/Create/Continue)
            # until the typed entity is actually selected.
            if (
                prev_subgoal is not None
                and prev_subgoal.action_type in ("type", "type_text", "enter_text", "set_text", "input_text")
                and action_type == "tap"
                and self._is_proceed_target(target)
            ):
                typed_entity = (prev_subgoal.target or "").strip()
                if typed_entity and self._looks_like_searchable_picker(prev_subgoal, ui_elements):
                    if not self._has_selected_evidence(ui_elements, typed_entity):
                        match_label = self._find_clickable_entity_match(ui_elements, typed_entity)
                        if match_label:
                            logger.info(
                                "🧭 Selection guard: '%s' not selected yet; overriding proceed tap '%s' with row tap '%s'",
                                typed_entity,
                                target,
                                match_label,
                            )
                            action_type = "tap"
                            target = match_label
                            description = (
                                f"Tap '{match_label}' to select it before proceeding"
                            )
                            phase_complete = False
                            goal_complete = False
                            verification_passed = True
                            verification_reason = (
                                f"Selection guard: must select '{typed_entity}' before '{target}'"
                            )

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
            if ask_user_options:
                subgoal.parameters["options"] = ask_user_options
            if not prev_step_ok and prev_step_issue:
                subgoal.parameters["__prev_step_ok__"] = False
                subgoal.parameters["__prev_step_issue__"] = prev_step_issue
                logger.warning(
                    f"ReactiveStepGenerator: prev step issue detected — {prev_step_issue[:100]}"
                )

            subgoal.parameters["__verification_passed__"] = verification_passed
            if verification_reason:
                subgoal.parameters["__verification_reason__"] = verification_reason
            # Forward VLM's accumulated memory to the next call via coordinator
            if memory:
                subgoal.parameters["__agent_memory__"] = memory

            # Persist SoM pre-resolved coordinates so the coordinator can skip
            # the perception step and use the exact pixel targets directly.
            if _som_tap_coords:
                subgoal.parameters["__resolved_coords__"] = _som_tap_coords
            if _som_swipe_params:
                subgoal.parameters.update(_som_swipe_params)

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
            # Show screen context for failures AND navigation-class successes so
            # the VLM knows what screen was reached after each transition.
            _show_screen = (m.result != "success") or (
                m.action_type in ("open_app", "navigate", "scroll_down", "scroll_up",
                                   "swipe", "back", "tap") and m.screen_description
            )
            if _show_screen and m.screen_description:
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

    # ── Recipient-field autocomplete detection ────────────────────────────────

    _RECIPIENT_FIELD_KEYWORDS = frozenset({"to", "recipient", "contact", "send to", "cc", "bcc"})
    # Resource-id fragments that identify recipient input fields in common apps
    _RECIPIENT_ID_FRAGMENTS = frozenset({"to", "recipient", "cc", "bcc", "contact", "email_to"})
    # Regex to recognise an email address in a UI element's text
    _EMAIL_RE = re.compile(r"[\w.+\-]+@[\w\-]+\.[a-z]{2,}", re.IGNORECASE)

    def _detect_autocomplete_suggestion(
        self,
        prev_subgoal: Optional[Subgoal],
        ui_elements,
    ) -> Optional[Subgoal]:
        """
        Deterministic pre-VLM check.

        If the previous action was a `type` into a recipient / contact field
        AND a clickable element matching the typed text is now visible in the
        current UI tree, return a tap-suggestion Subgoal immediately without
        calling the VLM.

        This handles the Gmail pattern where Android auto-advances focus to the
        body field while the 'To' autocomplete dropdown is still showing — the
        VLM sees EDIT+FOCUSED on body and says "no blockers", skipping the
        mandatory tap.

        Two independent detection strategies are combined with OR so that a
        missing/empty field_hint (Strategy 1) does not silently disable the
        whole check:

        Strategy 1 — field-hint driven (original):
            The previous Subgoal stored a __field_hint__ containing a recipient
            keyword ("to", "cc", …).  Requires the planning LLM to emit that
            field correctly.

        Strategy 2 — typed-text / UI-state driven (NEW — FIX-015):
            The typed text itself is an email address (contains "@"), which is
            almost exclusively entered into To/recipient fields.  No dependency
            on field_hint. Also fires when the UI tree contains a clickable
            element whose resource-id fragment identifies it as a recipient
            suggestion row, regardless of what field was focused.
        """
        if prev_subgoal is None:
            return None
        if prev_subgoal.action_type not in (
            "type", "type_text", "enter_text", "set_text", "input_text"
        ):
            return None

        field_hint = (prev_subgoal.parameters.get("__field_hint__") or "").lower().strip()
        typed_text = (prev_subgoal.target or "").lower().strip()

        if not typed_text:
            return None
        if not ui_elements:
            return None

        # ── Strategy 1: LLM-provided field_hint names a recipient field ──────
        strategy1_match = any(kw in field_hint for kw in self._RECIPIENT_FIELD_KEYWORDS)

        # ── Strategy 2: typed text is an email address (contains "@") ─────────
        # Email addresses are virtually never entered outside of To/CC/BCC fields.
        # Additionally scan the live UI tree: if any clickable element has a
        # resource-id fragment that marks it as a suggestion row, treat that as
        # a recipient-field context even when field_hint is absent.
        strategy2_match = "@" in typed_text or self._ui_has_recipient_suggestion_row(ui_elements)

        if not strategy1_match and not strategy2_match:
            return None

        detection_strategy = "field-hint" if strategy1_match else "email-pattern"

        # Scan for a clickable element whose text starts with or contains
        # the typed value (first match wins — suggestions are ranked by relevance).
        for el in ui_elements:
            if not self._el_clickable(el):
                continue
            el_text = self._el_text(el).strip()
            if not el_text:
                continue
            if el_text.lower().startswith(typed_text) or typed_text in el_text.lower():
                from config.success_criteria import get_success_criteria
                logger.info(
                    f"🎯 Autocomplete override [{detection_strategy}]: tapping '{el_text}' "
                    f"(typed='{typed_text}', field='{field_hint or 'auto-detected'}') — VLM bypassed"
                )
                subgoal = Subgoal(
                    description=f"Tap autocomplete suggestion '{el_text}' to confirm recipient",
                    action_type="tap",
                    target=el_text,
                    success_criteria=get_success_criteria("tap"),
                )
                subgoal.parameters["__autocomplete_override__"] = True
                subgoal.parameters["__autocomplete_strategy__"] = detection_strategy
                subgoal.parameters["__verification_passed__"] = True
                subgoal.parameters["__verification_reason__"] = (
                    f"Deterministic autocomplete [{detection_strategy}]: "
                    f"'{el_text}' matched typed '{typed_text}'"
                )
                return subgoal

        return None

    def _is_proceed_target(self, target: Optional[str]) -> bool:
        if not target:
            return False
        t = target.strip().lower()
        proceed_terms = {
            "next", "ok", "done", "continue", "create", "confirm", "save", "proceed", "submit"
        }
        return t in proceed_terms

    def _looks_like_searchable_picker(self, prev_subgoal: Subgoal, ui_elements) -> bool:
        field_hint = (prev_subgoal.parameters.get("__field_hint__") or "").lower().strip()
        desc = (prev_subgoal.description or "").lower()
        search_signal = any(k in field_hint or k in desc for k in (
            "search", "find", "name", "number", "contact", "recipient", "participant", "member"
        ))
        if not search_signal:
            return False
        if not ui_elements:
            return False
        # Picker-like screens usually include scroll containers with clickable rows.
        has_scroll = False
        has_clickable_rows = False
        for el in ui_elements:
            cls = ""
            if isinstance(el, dict):
                cls = (el.get("className") or "").lower()
                has_scroll = has_scroll or bool(el.get("scrollable") or el.get("isScrollable"))
                has_clickable_rows = has_clickable_rows or bool(el.get("clickable") or el.get("isClickable"))
            else:
                cls = (getattr(el, "className", "") or "").lower()
            has_scroll = has_scroll or any(k in cls for k in ("listview", "recyclerview", "scroll"))
        return has_scroll and has_clickable_rows

    def _has_selected_evidence(self, ui_elements, typed_entity: str) -> bool:
        typed = typed_entity.lower().strip()
        if not typed or not ui_elements:
            return False
        for el in ui_elements:
            text = self._el_text(el).lower().strip()
            if not text:
                continue
            if typed in text and any(k in text for k in ("selected", "checked", "is selected", "chosen", "added")):
                return True
        return False

    def _find_clickable_entity_match(self, ui_elements, typed_entity: str) -> Optional[str]:
        typed = typed_entity.lower().strip()
        if not typed or not ui_elements:
            return None
        for el in ui_elements:
            if not self._el_clickable(el):
                continue
            label = self._el_text(el).strip()
            if not label:
                continue
            l = label.lower()
            if l.startswith(typed) or typed in l:
                # Avoid re-tapping the input field that contains the typed query.
                if "edittext" in (self._el_class_name(el).lower()):
                    continue
                return label
        return None

    @staticmethod
    def _el_class_name(el) -> str:
        if isinstance(el, dict):
            return el.get("className") or ""
        return getattr(el, "className", "") or ""

    def _ui_has_recipient_suggestion_row(self, ui_elements) -> bool:
        """
        Return True if the current UI tree contains a clickable element whose
        resource-id fragment identifies it as a contact/recipient suggestion row.

        This is a secondary signal for Strategy 2: even if the typed text is
        not an email address, a visible suggestion row strongly implies the
        previous type action targeted a recipient field.
        """
        for el in ui_elements:
            if not self._el_clickable(el):
                continue
            res_id = self._el_resource_id(el).lower()
            if any(frag in res_id for frag in self._RECIPIENT_ID_FRAGMENTS):
                # Only count elements that also contain an email-looking string
                el_text = self._el_text(el)
                if self._EMAIL_RE.search(el_text):
                    return True
        return False

    @staticmethod
    def _el_clickable(el) -> bool:
        if isinstance(el, dict):
            return bool(el.get("isClickable") or el.get("clickable"))
        return bool(getattr(el, "clickable", False))

    @staticmethod
    def _el_text(el) -> str:
        if isinstance(el, dict):
            return (
                el.get("text")
                or el.get("contentDescription")
                or el.get("content_description")
                or ""
            )
        return (
            getattr(el, "text", None)
            or getattr(el, "content_description", None)
            or getattr(el, "contentDescription", None)
            or ""
        )

    @staticmethod
    def _el_resource_id(el) -> str:
        if isinstance(el, dict):
            return (
                el.get("resourceId")
                or el.get("resource_id")
                or el.get("viewIdResourceName")
                or ""
            )
        return (
            getattr(el, "resource_id", None)
            or getattr(el, "resourceId", None)
            or getattr(el, "viewIdResourceName", None)
            or ""
        )

    # ── Deterministic goal-completion detection ───────────────────────────────

    _NAVIGATION_GOAL_KEYWORDS = frozenset({
        "navigate", "navigation", "directions", "go to", "route to",
        "take me to", "drive to", "get directions", "open maps", "find route",
    })

    # Signals that ONLY appear on an active navigation screen, not on the
    # route-preview screen that still shows a "Start" button.
    _ACTIVE_NAV_SIGNALS = (
        "towards",           # green next-maneuver banner: "towards Madugarai Rd"
        "arriving at",       # arrival imminent
        "navigation started",
        "on your route",
        "continue on",
        "take the",          # turn-by-turn instructions
    )

    # Regex to detect a duration (e.g. "3hr 45min", "12 min", "1 hour 20 minutes")
    _TIME_RE = re.compile(r"\b\d+\s*(hr|min|hour|minute)s?\b", re.IGNORECASE)
    # Regex to detect a distance (e.g. "182 km", "5.3 mi", "400 m")
    _DIST_RE = re.compile(r"\b\d+[\d.]*\s*(km|mi|miles?|meters?)\b", re.IGNORECASE)

    def _detect_goal_achieved_from_screen(
        self,
        screen_context: str,
        original_utterance: str,
    ) -> bool:
        """
        Deterministic post-parse override.

        Returns True when the screen unambiguously shows the goal has been
        achieved, even if the LLM returned goal_complete=False.

        Currently handles:
        - Navigation tasks: screen shows an active turn-by-turn route with ETA
          and/or a "towards X Rd" next-maneuver banner.
        """
        if not screen_context:
            return False

        ctx = screen_context.lower()
        utterance = (original_utterance or "").lower()

        # ── Navigation goal detection ─────────────────────────────────────────
        is_nav_goal = any(kw in utterance for kw in self._NAVIGATION_GOAL_KEYWORDS)
        if not is_nav_goal:
            return False

        # Strong positive: a maneuver banner or explicit "navigation started" text
        has_strong_signal = any(sig in ctx for sig in self._ACTIVE_NAV_SIGNALS)

        # Weak positive: ETA + distance shown together (only valid during routing)
        has_time = bool(self._TIME_RE.search(ctx))
        has_distance = bool(self._DIST_RE.search(ctx))
        has_eta_combo = has_time and has_distance

        if not has_strong_signal and not has_eta_combo:
            return False

        # Negative guard: route-preview screen still shows a "Start" button —
        # navigation has NOT started yet.  Match only the button label, not
        # the word "start" appearing in other contexts.
        preview_indicators = ["start navigation", "tap start", "press start"]
        if any(ind in ctx for ind in preview_indicators):
            return False

        logger.info(
            "🎯 Goal-achieved override: active navigation detected in screen context "
            f"(strong={has_strong_signal}, eta_combo={has_eta_combo})"
        )
        return True

    # ─────────────────────────────────────────────────────────────────────────

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
