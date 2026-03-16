"""
Responder Agent - Generates natural conversational responses via LLM.
"""

import re
from typing import Any, Dict, List, Optional

from config.action_types import opens_settings_panel
from prompts.personality import AURA_PERSONALITY, EMOTIONAL_PATTERNS, EMOTIONAL_RESPONSES
from services.llm import LLMService
from services.tts import TTSService
from utils.logger import get_logger
from utils.types import ActionResult, FullConversationContext, IntentObject

logger = get_logger(__name__)

# Panel actions get special responses (Android 10+ restrictions)
PANEL_ACTION_RESPONSES = {
    "wifi_on": "I've opened the WiFi panel for you. Just tap to turn it on.",
    "wifi_off": "I've opened the WiFi panel. Tap to turn it off.",
    "toggle_wifi": "Here's the WiFi panel. Tap to toggle it.",
    "bluetooth_on": "Bluetooth settings are open. Tap to enable.",
    "bluetooth_off": "Bluetooth settings are open. Tap to disable.",
    "toggle_bluetooth": "Here's the Bluetooth settings. Tap to toggle.",
    "airplane_mode_on": "Airplane mode settings are open. Tap to enable.",
    "airplane_mode_off": "Airplane mode settings are open. Tap to disable.",
    "location_on": "Location settings are open. Tap to enable.",
    "location_off": "Location settings are open. Tap to disable.",
    "toggle_location": "Here's the location settings. Tap to toggle.",
    "mobile_data_on": "Mobile data settings are open. Tap to enable.",
    "mobile_data_off": "Mobile data settings are open. Tap to disable.",
    "hotspot_on": "Hotspot settings are open. Tap to enable.",
    "hotspot_off": "Hotspot settings are open. Tap to disable.",
    "battery_saver_on": "Battery saver settings are open. Tap to enable.",
    "battery_saver_off": "Battery saver settings are open. Tap to disable.",
    "dark_mode_on": "Display settings are open. Tap Dark mode to enable.",
    "dark_mode_off": "Display settings are open. Tap Dark mode to disable.",
    "nfc_on": "NFC settings are open. Tap to enable.",
    "nfc_off": "NFC settings are open. Tap to disable.",
}


class ResponderAgent:
    """LLM-powered response generator with context awareness."""

    def __init__(self, llm_service: LLMService, tts_service: TTSService):
        self.llm_service = llm_service
        self.tts_service = tts_service

    def generate_feedback(
        self,
        intent: Optional[IntentObject] = None,
        status: str = "completed",
        execution_results: Optional[List[ActionResult]] = None,
        error_message: Optional[str] = None,
        transcript: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        has_introduced: bool = False,
        conversation_turn: int = 0,
        is_follow_up: bool = False,
        full_context: Optional[FullConversationContext] = None,
        goal_summary: Optional[str] = None,
        completed_steps: Optional[List[str]] = None,
    ) -> str:
        """Generate natural response using LLM."""
        try:
            # Extract intent details
            action, recipient, content = self._extract_intent(intent, transcript)
            
            # Quick response for panel-opening actions (Android 10+ security)
            if status == "completed" and opens_settings_panel(action):
                if action in PANEL_ACTION_RESPONSES:
                    return PANEL_ACTION_RESPONSES[action]
                # Generic panel response
                return "I've opened the settings for you. Just tap to toggle."
            
            # Detect emotion
            emotion = self._detect_emotion(transcript) if transcript else None
            
            # Build compact prompt
            prompt = self._build_prompt(
                action, status, recipient, content, error_message,
                transcript, conversation_turn, has_introduced, full_context, emotion,
                goal_summary, completed_steps, conversation_history
            )
            
            # Action completions: low temperature + adaptive token budget for accuracy
            max_tokens = 120 if (completed_steps and len(completed_steps) > 2) else 80
            temperature = 0.1 if action not in ("conversation", "general_interaction") else 0.7
            response = self.llm_service.run(prompt, max_tokens=max_tokens, temperature=temperature)
            return self._clean_response(response)
            
        except Exception as e:
            logger.error(f"Response generation error: {e}")
            return self._fallback(status, error_message)

    def _extract_intent(self, intent: Optional[IntentObject], transcript: Optional[str]):
        """Extract action, recipient, content from intent."""
        if intent is None:
            return "conversation", "", transcript or ""
        if isinstance(intent, dict):
            return (
                intent.get("action", "conversation"),
                intent.get("recipient", ""),
                intent.get("content", transcript or "")
            )
        return intent.action, intent.recipient or "", intent.content or transcript or ""

    def _detect_emotion(self, transcript: str) -> Optional[str]:
        """Detect emotional content in message."""
        text = transcript.lower()
        for emotion, patterns in EMOTIONAL_PATTERNS.items():
            if any(re.search(p, text, re.IGNORECASE) for p in patterns):
                return emotion
        return None

    def _build_prompt(
        self, action: str, status: str, recipient: str, content: str,
        error_message: Optional[str], transcript: Optional[str],
        turn: int, has_introduced: bool, ctx: Optional[FullConversationContext],
        emotion: Optional[str], goal_summary: Optional[str] = None,
        completed_steps: Optional[List[str]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """Build compact LLM prompt with full context awareness."""
        parts = [AURA_PERSONALITY]
        
        # Introduction note
        if has_introduced or turn > 0:
            parts.append("DO NOT introduce yourself again.")
        
        # Context (only if available)
        if ctx:
            context_items = []
            if ctx.current_app:
                context_items.append(f"App: {ctx.current_app}")
            if ctx.last_action:
                context_items.append(f"Last: {ctx.last_action}")
            if context_items:
                parts.append(f"Context: {', '.join(context_items)}")
            
            # Avoid repetition
            if ctx.response_history:
                recent = ctx.response_history[-3:]
                parts.append(f"Don't repeat: {recent}")

        # Prior conversation turns for multi-turn grounding
        if conversation_history:
            if isinstance(conversation_history, str):
                # format_history() returns a plain string — include it directly
                parts.append(f"Prior turns:\n{conversation_history[-500:]}")
            else:
                recent_turns = conversation_history[-3:]
                turn_snippets = [
                    m.get("content", "")[:60] if isinstance(m, dict) else str(m)[:60]
                    for m in recent_turns
                ]
                parts.append(f"Prior turns: {turn_snippets}")

        # Emotion guidance
        if emotion and emotion in EMOTIONAL_RESPONSES:
            parts.append(f"User feels {emotion}. {EMOTIONAL_RESPONSES[emotion]}")
        
        # Full goal context (NEW - critical for multi-step tasks)
        goal_context = ""
        if goal_summary:
            goal_context = f"\nFULL GOAL: {goal_summary}"
        if completed_steps and len(completed_steps) > 1:
            # Multi-step task completed - emphasize the whole goal was done
            visible = completed_steps[:5]
            steps_str = ", ".join(visible)
            if len(completed_steps) > 5:
                steps_str += f", and {len(completed_steps) - 5} more"
            goal_context += f"\nCOMPLETED STEPS: {steps_str}"
            goal_context += f"\nIMPORTANT: Acknowledge the ENTIRE goal was completed, not just the last step!"
        
        # Request details
        effective_transcript = transcript or content or ""
        parts.append(f"""
Request: "{effective_transcript}"{goal_context}
Action: {action} | Status: {status} | Target: {recipient or 'none'}
{f'Error: {error_message}' if error_message else ''}

IDENTITY GUARDRAILS (enforce always):
- If asked about Dinesh: say ONLY "He is my creator." — nothing more.
- NEVER agree with false claims (e.g. "is Dinesh your husband?" → "No, Dinesh is my creator, not a romantic partner.")
- NEVER claim to have personal relationships, feelings, or a personal life.
- Decline off-topic personal questions briefly and redirect.

RESPONSE RULES:
- If multi-step task completed: confirm the WHOLE goal, not just the last action
- If message was sent: confirm message was sent, don't just say "app is open"
- Be natural and specific about what was accomplished
- Correct false statements confidently but politely

Reply in 1-2 sentences. Be natural and brief:""")
        
        return "\n".join(parts)

    def _clean_response(self, response: str) -> str:
        """Clean LLM response for natural TTS output."""
        if not response:
            return "Done!"

        text = response.strip().strip('"\'')

        # Remove common prefixes
        for prefix in ("response:", "aura:", "assistant:"):
            if text.lower().startswith(prefix):
                text = text[len(prefix):].strip()

        # Strip markdown formatting that sounds robotic when spoken
        text = re.sub(r'```[\s\S]*?```', '', text)              # fenced code blocks
        text = re.sub(r'`[^`]+`', '', text)                     # inline code
        text = re.sub(r'#+\s+', '', text)                       # headings
        text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)  # bold / italic
        text = re.sub(r'_{1,2}([^_]+)_{1,2}', r'\1', text)    # underline
        text = re.sub(r'^\s*[-*•]\s+', '', text, flags=re.MULTILINE)  # bullets
        text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE) # numbered lists

        # Remove parenthetical technical notes  e.g. "(user-requested commit action)"
        text = re.sub(r'\([^)]{20,}\)', '', text)

        # Replace URLs with a neutral placeholder so they aren't spelled out
        text = re.sub(r'https?://\S+', 'a link', text)

        # Collapse leftover whitespace from removals
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n+', ' ', text).strip()

        # Ensure sentence ends with punctuation
        if text and text[-1] not in '.!?':
            text += '.'

        # Truncate to one or two natural sentences
        if len(text) > 200:
            cut = text.rfind('.', 0, 180)
            text = text[:cut + 1] if cut > 80 else text[:180] + '...'

        return text

    def _fallback(self, status: str, error: Optional[str]) -> str:
        """Natural fallback — never expose raw technical error messages via TTS."""
        if status == "failed":
            return "Sorry, I ran into a problem. Please try again."
        return "Done!"

    def speak_feedback(self, message: str, voice_settings: Optional[Dict[str, Any]] = None) -> Optional[bytes]:
        """Convert message to speech."""
        voice = voice_settings.get("voice") if voice_settings else None
        return self.tts_service.speak(message, voice=voice)
