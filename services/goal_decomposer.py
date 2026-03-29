"""
Goal Decomposer - Breaks complex goals into executable subgoals.

Uses LLM to intelligently plan multi-step tasks without
hardcoded app-specific knowledge.
"""

import json
import re
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from aura_graph.agent_state import Goal, Phase, StepMemory, Subgoal, SuccessCriteria
from config.success_criteria import get_success_criteria
from prompts import get_planning_prompt, get_replanning_prompt
from prompts.skeleton_planning import get_skeleton_planning_prompt
from services.llm import LLMService
from utils.logger import get_logger

if TYPE_CHECKING:
    from perception.models import PerceptionBundle

logger = get_logger(__name__)


class GoalDecomposer:
    """
    Decomposes complex user goals into executable subgoals.
    
    Uses LLM reasoning to plan tasks without app-specific templates.
    Can replan dynamically when obstacles are encountered.
    """

    def __init__(self, llm_service: LLMService):
        self.llm_service = llm_service

    def decompose(
        self,
        utterance: str,
        current_screen: Optional["PerceptionBundle"] = None,
        step_history: Optional[List[StepMemory]] = None,
        web_hints: str = "",
    ) -> Goal:
        """
        Decompose a user utterance into a Goal with skeleton phases.

        Layer 1 (here): generate 2-4 abstract phases + commit actions.
        Layer 2 (Coordinator + ReactiveStepGenerator): resolve each phase to
        concrete UI steps grounded in the live screen, one step at a time.
        """
        logger.info(f"🎯 Decomposing goal: {utterance}")

        screen_context = self._extract_screen_context(current_screen)

        if step_history:
            history_lines = [
                f"{'✅' if m.result == 'success' else '❌'} {m.action_type}({m.target or ''})"
                for m in step_history[-3:]
            ]
            screen_context = screen_context + " | Recent steps: " + " → ".join(history_lines)

        phases, commit_actions, summary = self._create_skeleton(utterance, screen_context, web_hints=web_hints)

        goal = Goal(
            original_utterance=utterance,
            description=summary,
            phases=phases,
            pending_commits=commit_actions,
        )

        logger.info(f"📋 Skeleton plan: {len(phases)} phases, commits={commit_actions}")
        for i, ph in enumerate(phases, 1):
            logger.info(f"   Phase {i}: {ph.description}")

        return goal

    def replan_from_obstacle(
        self,
        goal: Goal,
        obstacle: str,
        current_screen: Optional["PerceptionBundle"] = None,
        step_history: Optional[List[StepMemory]] = None,
    ) -> List[Subgoal]:
        """
        Create new subgoals to overcome an obstacle.
        
        Args:
            goal: Current goal being worked on
            obstacle: Description of what's blocking progress
            current_screen: Current screen state
            step_history: Completed step memory for richer replanning context
        
        Returns:
            List of new subgoals to try
        """
        logger.info(f"🔄 Replanning due to obstacle: {obstacle}")
        
        screen_context = self._extract_screen_context(current_screen)
        
        # Build context about what's been tried
        completed = [sg.description for sg in goal.subgoals if sg.completed]
        current = goal.current_subgoal.description if goal.current_subgoal else "None"

        # Enrich screen context with step history if available
        if step_history:
            history_lines = []
            for mem in step_history[-5:]:   # last 5 steps for brevity
                status = "✅" if mem.result == "success" else "❌"
                line = f"{status} {mem.action_type}({mem.target or ''}) on {mem.screen_type} screen"
                # Include VLM description when available — critical for WebView steps
                # where the LLM must understand what was visible (product cards, etc.)
                if mem.screen_description:
                    line += f' [screen: "{mem.screen_description[:120]}"]'
                history_lines.append(line)
            screen_context = screen_context + " | History: " + " → ".join(history_lines)
        
        # Steps still pending after the current blocker — the recovery LLM must
        # know what still needs to happen so it doesn't regenerate the entire plan.
        remaining = [
            sg.description for sg in goal.subgoals
            if not sg.completed and sg is not goal.current_subgoal
        ]

        # Use centralized replanning prompt
        prompt = get_replanning_prompt(
            goal=goal.description,
            completed_steps=", ".join(completed) if completed else "None",
            current_step=current,
            obstacle=obstacle,
            screen_context=screen_context,
            remaining_steps=", ".join(remaining) if remaining else "None",
        )

        try:
            # Replanning doesn't need browser search — all context is inline.
            # No tools = no Groq "JSON tool" confusion; response_format is safe.
            # Large max_tokens budget: Gemini 2.5 Flash thinking models consume
            # hundreds of tokens for internal reasoning before emitting output.
            result = self.llm_service.run(
                prompt,
                max_tokens=1500,
                provider=self.llm_service.settings.planning_provider,
                model=self.llm_service.settings.planning_model,
                response_format={"type": "json_object"},
            )
            parsed = self._parse_json_response(result)
            
            if parsed and parsed.get("subgoals"):
                subgoals = []
                for sg_data in parsed["subgoals"]:
                    action_type = sg_data.get("action_type", "tap")
                    target = sg_data.get("target")
                    criteria = get_success_criteria(action_type)
                    if action_type == "open_app" and target and criteria.target_screen_reached is not None:
                        criteria.target_screen_reached = target.lower()
                    subgoals.append(Subgoal(
                        description=sg_data.get("description", ""),
                        action_type=action_type,
                        target=target,
                        success_criteria=criteria,
                    ))
                
                logger.info(f"📋 Replan generated {len(subgoals)} alternative subgoals")
                return subgoals
                
        except Exception as e:
            logger.error(f"Replanning failed: {e}")
        
        return []

    def _create_skeleton(
        self,
        utterance: str,
        screen_context: str,
        web_hints: str = "",
    ):
        """
        Call the LLM to generate a skeleton plan: 2-4 abstract phases.

        Returns:
            Tuple of (phases: List[Phase], commit_actions: List[str], summary: str)
        """
        from utils.app_inventory_utils import get_app_inventory_manager
        try:
            app_inventory = get_app_inventory_manager().get_installed_app_names()
        except Exception:
            app_inventory = ""

        prompt = get_skeleton_planning_prompt(utterance, screen_context, app_inventory, web_hints=web_hints)
        try:
            result = self.llm_service.run(
                prompt,
                max_tokens=300,
                provider=self.llm_service.settings.planning_provider,
                model=self.llm_service.settings.planning_model,
                response_format={"type": "json_object"},
            )
            parsed = self._parse_json_response(result)
        except Exception as e:
            logger.error(f"Skeleton planning LLM call failed: {e}")
            parsed = None

        phases: List[Phase] = []
        commit_actions: List[str] = []
        summary = self._summarize_goal(utterance)

        if parsed:
            summary = parsed.get("goal_summary") or summary
            commit_actions = [c for c in (parsed.get("commit_actions") or []) if isinstance(c, str)]
            raw_phases = parsed.get("phases") or []
            for p in raw_phases:
                if isinstance(p, str) and p.strip():
                    phases.append(Phase(description=p.strip()))
                elif isinstance(p, dict) and p.get("description"):
                    phases.append(Phase(description=str(p["description"]).strip()))

        if not phases:
            logger.warning("Skeleton planning returned no phases — using single fallback phase")
            phases = [Phase(description=f"Complete: {utterance}")]

        return phases, commit_actions, summary

    def _plan_with_llm(
        self,
        utterance: str,
        screen_context: str,
    ) -> List[Subgoal]:
        """Use LLM to create subgoal plan."""
        
        # Use centralized planning prompt (v2.0)
        prompt = get_planning_prompt(utterance, screen_context)

        # Retry up to 2 times on parse failure
        max_retries = 2
        parsed = None
        
        for attempt in range(max_retries):
            try:
                prompt_for_attempt = prompt
                if attempt > 0:
                    prompt_for_attempt += (
                        "\n\nCRITICAL RETRY CONSTRAINTS:\n"
                        "- Previous plan missed required side-effect steps.\n"
                        "- Include all mandatory commit actions from the user goal.\n"
                        "- For cart goals, include explicit 'Add to Cart' before any cart verification.\n"
                    )

                # Use planning provider (NVIDIA NIM or Gemini) for goal decomposition
                # Enable thinking mode for nvidia provider
                extra_kwargs = {}
                if self.llm_service.settings.planning_provider == "nvidia":
                    extra_kwargs["thinking"] = {"budget_tokens": 2048}

                result = self.llm_service.run(
                    prompt_for_attempt,
                    max_tokens=800,
                    provider=self.llm_service.settings.planning_provider,
                    model=self.llm_service.settings.planning_model,
                    response_format={"type": "json_object"},
                    **extra_kwargs,
                )
                parsed = self._parse_json_response(result)
                
                if parsed and parsed.get("subgoals"):
                    if not self._plan_covers_critical_requirements(utterance, parsed.get("subgoals", [])):
                        logger.warning(
                            f"Plan missing critical requirements (attempt {attempt + 1}), retrying",
                        )
                        if attempt < max_retries - 1:
                            continue
                    break  # Success, exit retry loop
                elif attempt < max_retries - 1:
                    logger.warning(f"LLM response parse failed (attempt {attempt + 1}), retrying...")
                    continue
                    
            except Exception as e:
                logger.error(f"LLM planning attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    continue
        
        if parsed and parsed.get("subgoals"):
            subgoals = []
            for sg_data in parsed["subgoals"]:
                action_type = sg_data.get("action_type", "tap")
                target = sg_data.get("target")

                # Use registered criteria for known action types
                criteria = get_success_criteria(action_type)

                # For open_app, set target_screen_reached to app name
                if action_type == "open_app" and target and criteria.target_screen_reached is not None:
                    criteria.target_screen_reached = target.lower()

                subgoals.append(Subgoal(
                    description=sg_data.get("description", ""),
                    action_type=action_type,
                    target=target,
                    success_criteria=criteria,
                ))
            
            return subgoals
        
        return []

    def _plan_covers_critical_requirements(self, utterance: str, raw_subgoals: List[Dict[str, Any]]) -> bool:
        """Deterministic guard: ensure plan doesn't miss mandatory user-requested commit actions."""
        utterance_lower = (utterance or "").lower()
        combined_steps = " ".join(
            f"{(sg.get('description') or '').lower()} {(sg.get('target') or '').lower()}"
            for sg in raw_subgoals
        )

        asks_add_to_cart = any(token in utterance_lower for token in ("to cart", "add to cart", "basket"))
        if asks_add_to_cart:
            has_add_to_cart = any(
                token in combined_steps
                for token in ("add to cart", "add-to-cart", "add item", "add to basket")
            )
            if not has_add_to_cart:
                return False

        asks_send = any(token in utterance_lower for token in ("send", "submit", "confirm"))
        if asks_send:
            has_send_like = any(token in combined_steps for token in ("send", "submit", "confirm"))
            if not has_send_like:
                return False

        return True

    def _extract_screen_context(
        self,
        bundle: Optional["PerceptionBundle"],
    ) -> str:
        """
        Extract relevant context from current screen.

        Priority:
        1. bundle.visual_description — VLM-generated semantic summary. This is
           the richest source and correctly describes WebView screens (product
           cards, search results) that the accessibility tree can't see.
        2. UI tree elements — fast textual fallback when no VLM description is
           available (standard native screens).
        """
        if not bundle:
            return "Unknown (no screen data)"

        # ── Priority 1: VLM semantic description ─────────────────────────────
        # Generated by ScreenVLM when skip_description=False.
        # Covers WebView content the UI tree is blind to.
        if bundle.visual_description:
            # Prepend app name from UI tree if available, then VLM description
            app_name = ""
            if bundle.ui_tree and bundle.ui_tree.elements:
                root = bundle.ui_tree.elements[0]
                pkg = root.get("packageName", "")
                if pkg:
                    app_name = pkg.split(".")[-1]

            prefix = f"App: {app_name} | " if app_name else ""
            return prefix + bundle.visual_description.strip()

        # ── Priority 2: UI tree element scraping ─────────────────────────────
        parts = []

        if bundle.ui_tree and bundle.ui_tree.elements:
            root = bundle.ui_tree.elements[0] if bundle.ui_tree.elements else {}
            package = root.get("packageName", "")
            if package:
                app_name = package.split(".")[-1]
                parts.append(f"App: {app_name}")

            texts = []
            buttons = []
            for elem in bundle.ui_tree.elements:
                text = elem.get("text") or elem.get("contentDescription")
                if text and len(text) < 50:
                    texts.append(text)
                is_clickable = elem.get("clickable") or elem.get("isClickable")
                if is_clickable and text:
                    buttons.append(text[:30])

            if texts:
                unique_texts = list(dict.fromkeys(texts))[:12]
                parts.append(f"Visible: {', '.join(unique_texts)}")
            if buttons:
                unique_buttons = list(dict.fromkeys(buttons))[:10]
                parts.append(f"Buttons: {', '.join(unique_buttons)}")
        else:
            parts.append("Home screen or app launcher")

        return " | ".join(parts) if parts else "Unknown screen"

    def _summarize_goal(self, utterance: str) -> str:
        """Create a clean goal description from utterance."""
        # Simple cleanup - could use LLM for complex cases
        cleaned = utterance.strip()
        
        # Remove common prefixes
        prefixes = ["please ", "can you ", "i want to ", "i need to ", "could you "]
        for prefix in prefixes:
            if cleaned.lower().startswith(prefix):
                cleaned = cleaned[len(prefix):]
                break
        
        return cleaned.capitalize()

    def _parse_json_response(self, response: str) -> Optional[Dict[str, Any]]:
        """Parse JSON from LLM response."""
        if not response:
            return None

        # Some providers may return non-str values; be defensive.
        if not isinstance(response, str):
            try:
                response = str(response)
            except Exception:
                return None

        text = response.strip()

        # Strip BOM / zero-width chars that can break json parsing.
        text = text.lstrip("\ufeff\u200b\u200c\u200d")
        
        # Remove markdown code blocks
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)

        # Normalize a few common "JSON-ish" issues from LLMs.
        # - Smart quotes
        # - Trailing commas before } or ]
        text = text.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
        text = re.sub(r",\s*([}\]])", r"\1", text)

        decoder = json.JSONDecoder()

        def _try_load_first_object(candidate: str) -> Optional[Dict[str, Any]]:
            """Parse the first JSON object from a string that may contain trailing text."""
            try:
                obj, _end = decoder.raw_decode(candidate)
                return obj if isinstance(obj, dict) else None
            except Exception:
                return None

        # 1) Direct parse.
        direct = _try_load_first_object(text)
        if direct is not None:
            return direct

        # 2) Try extracting the first JSON object from mixed text.
        first_obj = text.find("{")
        if first_obj != -1:
            extracted = _try_load_first_object(text[first_obj:])
            if extracted is not None:
                return extracted

        # 3) Some models return a JSON array; accept it only if it contains a single object.
        first_arr = text.find("[")
        last_arr = text.rfind("]")
        if first_arr != -1 and last_arr != -1 and last_arr > first_arr:
            try:
                parsed_arr = json.loads(text[first_arr:last_arr + 1])
                if isinstance(parsed_arr, list) and len(parsed_arr) == 1 and isinstance(parsed_arr[0], dict):
                    return parsed_arr[0]
            except Exception:
                pass

        logger.warning("Failed to parse LLM JSON response")
        logger.debug(f"LLM JSON parse failure (first 200 chars): {text[:200]}")
        return None


def decompose_simple_command(utterance: str, action: str, target: str = None) -> Goal:
    """
    Create a simple single-subgoal Goal without LLM.
    
    Used for simple commands that don't need decomposition.
    """
    subgoal = Subgoal(
        description=utterance,
        action_type=action,
        target=target,
    )
    
    return Goal(
        original_utterance=utterance,
        description=utterance,
        subgoals=[subgoal],
    )
