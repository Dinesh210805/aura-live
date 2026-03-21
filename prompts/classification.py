"""
Intent Classification & Parsing Prompts - v2.0.0

Prompts for understanding user intent and routing.

Changes from v1:
- Added modern action patterns (voice notes, reels, AI queries)
- Better conversational vs action distinction
- Clearer complexity classification
"""

import re
from typing import Optional


# =============================================================================
# INTENT PARSING — single base template with optional context
# =============================================================================
_INTENT_PARSING_BASE = """Parse this voice command into structured intent. Return ONLY valid JSON.

COMMAND: "{transcript}"
{context_section}
━━━ IMPORTANT RULES ━━━
1. "tap/click/press on X" → action=TAP (even if X contains "send")
2. "send message to X" → action=SEND_MESSAGE (actually sending)
3. App drawer is SYSTEM navigation, not an app name
4. Complex app goals: Use parameters, NOT steps array

━━━ EXAMPLES ━━━
Basic:
- "open WhatsApp" → {{"action":"open_app","recipient":"WhatsApp","confidence":0.95}}
- "tap send button" → {{"action":"tap","recipient":"send button","confidence":0.95}}
- "press back" → {{"action":"back","confidence":0.95}}
- "scroll down" → {{"action":"scroll","parameters":{{"direction":"down"}},"confidence":0.95}}

Messaging:
- "send hi to John" → {{"action":"send_message","recipient":"John","content":"hi","confidence":0.9}}
- "call Mom" → {{"action":"make_call","recipient":"Mom","confidence":0.95}}

System:
- "open app drawer" → {{"action":"navigate_app","parameters":{{"target":"app_drawer"}},"confidence":0.95}}
- "take screenshot" → {{"action":"take_screenshot","confidence":0.95}}
- "what's on screen" → {{"action":"read_screen","confidence":0.95}}

Modern:
- "record voice note" → {{"action":"record_audio","parameters":{{"type":"voice_note"}},"confidence":0.9}}
- "play this reel" → {{"action":"tap","recipient":"reel_video","confidence":0.85}}
- "summarize this page" → {{"action":"read_screen","parameters":{{"mode":"summarize"}},"confidence":0.9}}

App Goals:
- "play my liked songs on Spotify" → {{"action":"open_app","recipient":"spotify","parameters":{{"goal":"play_liked_songs"}},"confidence":0.9}}

━━━ MULTI-STEP COMMANDS ━━━
If the command chains 3+ distinct actions OR uses connectors like "then", "and then", "after that":
→ {{"action":"general_interaction","content":"<full command>","confidence":0.85,"parameters":{{"delegate_to_planner":true}}}}
Do NOT try to parse recipient/content from multi-step commands — let the planner decompose them.

━━━ SCOPE ━━━
You ONLY classify the command into a single action type. You do NOT decompose multi-step goals — that is the Planner's job.

OUTPUT ONLY JSON (include thinking first, it is ignored after parsing):
{{"thinking":"brief reasoning about what action type fits","action":"...","recipient":"...","content":"...","parameters":{{}},"confidence":0.0-1.0,"ambiguities":[]}}"""

_CONTEXT_SECTION = """
━━━ CONVERSATION CONTEXT ━━━
{context_block}

━━━ CONTEXT RULES ━━━
- If the command relates to the current app and no other app is mentioned, set recipient to the CURRENT APP.
- If the user explicitly names a DIFFERENT app, use that app instead.
- If the command is unrelated to any app (e.g. "turn on wifi"), ignore the context.
"""

# Backward-compatible constants: pre-built from the base template
INTENT_PARSING_PROMPT = _INTENT_PARSING_BASE.replace("{context_section}", "")
INTENT_PARSING_PROMPT_WITH_CONTEXT = _INTENT_PARSING_BASE.replace(
    "{context_section}", _CONTEXT_SECTION
)


# =============================================================================
# INTENT CLASSIFICATION PROMPT (Fuzzy Classifier)
# =============================================================================
INTENT_CLASSIFICATION_PROMPT = """Classify this request for a mobile voice assistant.

━━━ CATEGORIES ━━━

**CONVERSATIONAL**: Just talking, NO device action needed
- Greetings: "hi", "hello", "good morning"
- Help: "what can you do", "help me"
- Status: "how are you"
- Thanks: "thank you"
→ Requires: responder only

**SIMPLE**: Single, direct command (no screen analysis needed)
- "take screenshot", "scroll down", "press back"
- "turn on WiFi", "increase volume"
- "open WhatsApp"
→ Requires: commander → executor → responder

**MEDIUM**: Needs to see/understand screen
- "what's on my screen", "describe this"
- "read the screen", "what do you see"
- "find the settings button"
→ Requires: commander → navigator → responder

**COMPLEX**: Multi-step workflow with planning
- "send John a WhatsApp message saying hi"
- "search for bluetooth in settings"
- "play my liked songs on Spotify"
→ Requires: full pipeline with planning

━━━ CRITICAL RULE ━━━
"what is on my screen" = MEDIUM (needs screen capture), NOT conversational!

━━━ OUTPUT (JSON ONLY) ━━━
{{
  "complexity": "conversational|simple|medium|complex",
  "reasoning": "Brief explanation",
  "confidence": 0.0-1.0,
  "requires_ui_analysis": true|false,
  "requires_execution": true|false,
  "suggested_agents": ["responder"] or ["commander", "executor", "responder"] etc.
}}"""


# =============================================================================
# VISUAL REFERENCE PATTERNS (compiled regex for performance)
# =============================================================================
VISUAL_PATTERNS = re.compile(
    r"\b(red|blue|green|yellow|orange|purple|pink|black|white|gr[ae]y|"
    r"first|second|third|top|bottom|left|right|middle|"
    r"icon|button|image|above|below|next to|this|that|it)\b",
    re.IGNORECASE
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================
def get_classification_prompt() -> str:
    """Get the intent classification system prompt."""
    return INTENT_CLASSIFICATION_PROMPT


def get_parsing_prompt(transcript: str) -> str:
    """Build intent parsing prompt with transcript."""
    return INTENT_PARSING_PROMPT.format(transcript=transcript)
