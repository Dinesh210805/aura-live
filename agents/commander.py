"""
Commander Agent - Converts voice commands to structured intents.
Uses rule-based classification (fast) with LLM fallback (accurate).
"""

import json
import re
from typing import Any, Dict, Optional

from prompts import INTENT_PARSING_PROMPT, INTENT_PARSING_PROMPT_WITH_CONTEXT, VISUAL_PATTERNS
from services.llm import LLMService
from services.task_progress import get_task_progress_service
from utils.logger import get_logger
from utils.types import IntentObject

logger = get_logger(__name__)


class CommanderAgent:
    """Rule-based + LLM intent parser."""

    def __init__(self, llm_service: LLMService):
        self.llm_service = llm_service
        self.rule_classifier = None
        
        try:
            from utils.rule_based_classifier import get_rule_classifier
            self.rule_classifier = get_rule_classifier()
            logger.info("✅ Commander initialized (rule + LLM)")
        except Exception as e:
            logger.warning(f"Rule classifier unavailable: {e}")

    def _build_context_block(self, context: Dict[str, Any]) -> str:
        """Build a concise context string for the LLM prompt."""
        parts = []
        if context.get("current_app"):
            parts.append(f"Current app: {context['current_app']}")
        if context.get("last_action"):
            parts.append(f"Last action: {context['last_action']}")
        if context.get("last_target"):
            parts.append(f"Last target: {context['last_target']}")
        if context.get("screen_elements"):
            visible = [
                e.get("text") or e.get("contentDescription", "")
                for e in context["screen_elements"][:8]
                if e.get("text") or e.get("contentDescription")
            ]
            if visible:
                parts.append(f"Visible UI: {', '.join(visible[:6])}")
        if context.get("screen_description"):
            parts.append(f"Screen: {context['screen_description'][:120]}")
        return "\n".join(parts) if parts else ""

    def _parse_direct(self, transcript: str, context: Optional[Dict[str, Any]] = None) -> IntentObject:
        """Parse intent using LLM, with optional conversation context."""
        result = None
        try:
            context_block = self._build_context_block(context) if context else ""
            if context_block:
                prompt = INTENT_PARSING_PROMPT_WITH_CONTEXT.format(
                    transcript=transcript, context_block=context_block
                )
            else:
                prompt = INTENT_PARSING_PROMPT.format(transcript=transcript)

            result = self.llm_service.run(
                prompt,
                max_tokens=400,
                response_format={"type": "json_object"},
                caller_agent="commander",  # G11: attribute tokens to commander
            )

            # Strip markdown fences that some models add despite json_object mode
            result = result.strip()
            if result.startswith("```"):
                result = result.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            # Parse — handle array response (model returned multiple candidates)
            raw = json.loads(result)
            if isinstance(raw, list):
                raw = max(raw, key=lambda x: x.get("confidence", 0))

            # Strip scratchpad fields not part of IntentObject schema
            thinking = raw.pop("thinking", None)
            raw.pop("ambiguities", None)
            if thinking:
                logger.debug(f"Commander thinking: {thinking[:80]}")

            raw["action"] = self._normalize_action(raw.get("action", "general_interaction"))
            raw = self._normalize_intent_fields(raw)

            # Add visual reference flag if detected
            if VISUAL_PATTERNS.search(transcript):
                raw.setdefault("parameters", {})["visual_reference"] = True

            intent = IntentObject.model_validate(raw)
            logger.debug(
                f"Parsed intent: action={intent.action}, recipient={intent.recipient}, "
                f"content={intent.content}, parameters={intent.parameters}"
            )
            return intent

        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Parse failed: {e} | raw={result[:200] if result else 'N/A'}")
            return self._fallback_intent(transcript, "parse_error")
        except Exception as e:
            logger.error(f"Parse failed: {e}")
            return self._fallback_intent(transcript, str(e))
    
    def _fallback_intent(self, transcript: str, error: str) -> IntentObject:
        """Create fallback intent for errors."""
        return IntentObject(
            action="general_interaction",
            recipient=None,
            content=transcript,
            parameters={"error": error},
            confidence=0.3
        )

    def parse_intent(self, transcript: str, context: Optional[Dict[str, Any]] = None) -> IntentObject:
        """Parse transcript using rules first, then LLM with conversation context."""
        get_task_progress_service().emit_agent_status("Commander", f"Parsing: '{transcript[:40]}...'")
        
        if self.rule_classifier:
            rule_intent = self.rule_classifier.classify(transcript)
            if rule_intent and rule_intent.get("confidence", 1.0) >= 0.85:
                # If rule matched but has no recipient and context has current_app,
                # inject it for app-related actions
                if context and not rule_intent.get("recipient") and context.get("current_app"):
                    action = rule_intent.get("action", "")
                    if action in ("open_app", "play_media", "search", "navigate"):
                        rule_intent["recipient"] = context["current_app"]
                logger.info(f"⚡ Rule match: {rule_intent['action']}")
                get_task_progress_service().emit_agent_status("Commander", f"Detected: {rule_intent['action']}")
                return IntentObject(**rule_intent)
        
        return self._parse_direct(transcript, context)

    def _normalize_action(self, action: str) -> str:
        """Normalize action to standard format."""
        action = action.lower().replace(" ", "_").replace("-", "_")
        
        aliases = {
            "open": "open_app", "launch": "open_app", "start": "open_app",
            "send_text": "send_message", "message": "send_message",
            "dial": "make_call", "phone_call": "make_call",
            "capture_screen": "take_screenshot", "screenshot": "take_screenshot"
        }
        
        return aliases.get(action, action)

    def _normalize_intent_fields(self, intent_data: Dict[str, Any]) -> Dict[str, Any]:
        """Move data to correct fields based on action type."""
        action = intent_data.get("action", "").lower()
        params = intent_data.get("parameters", {})
        
        if action == "open_app":
            intent_data["recipient"] = (
                intent_data.get("recipient") or 
                intent_data.get("content") or 
                params.get("app_name")
            )
            intent_data["content"] = None
            
        elif action == "send_message":
            intent_data["recipient"] = intent_data.get("recipient") or params.get("recipient") or params.get("contact")
            intent_data["content"] = intent_data.get("content") or params.get("message") or params.get("text")
        
        return intent_data

    def validate_intent(self, intent: IntentObject) -> bool:
        """Check if intent is actionable."""
        if not intent.action or intent.action == "unknown" or intent.confidence < 0.3:
            return False
        
        if intent.action == "send_message":
            return bool(intent.recipient and intent.content)
        
        if intent.action == "open_app":
            return bool(intent.recipient)
        
        return True
        