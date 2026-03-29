"""
LangGraph conditional edges for the AURA backend.

This module defines the conditional logic that determines
the flow between nodes in the AURA task execution graph.
Uses fuzzy logic for intelligent agent routing.
"""

import re
from typing import Literal

# Compiled once at import time — word-boundary match for conversational transcripts.
# Substring matching ("hi" in "I need to open WhatsApp") causes false positives.
_CONVERSATIONAL_TRANSCRIPT_RE = re.compile(
    r"\b(?:hello|hi|hey|help|bye|thanks|thank\s+you|"
    r"good\s+(?:morning|evening|night)|who\s+are\s+you|what\s+can\s+you\s+do)\b",
    re.IGNORECASE,
)

from config.action_types import (
    CONVERSATIONAL_ACTIONS,
    COORDINATE_REQUIRING_ACTIONS,
    NO_SCREEN_ACTIONS,
    NO_UI_ACTIONS,
    SIMPLE_DEVICE_ACTIONS,
    WEB_SEARCH_ACTIONS,
)
from utils.logger import get_logger

from .state import TaskState

logger = get_logger(__name__)

# FIXED: FIX-012 — cache settings at import time to avoid Pydantic overhead
# on every graph transition. Settings are read-only after startup.
from config.settings import get_settings as _get_settings
_SETTINGS = _get_settings()


def route_from_start(state: TaskState) -> Literal["stt", "parse_intent", "error_handler"]:
    """
    Route from the start node based on input type.
    
    Args:
        state: Current task state.
    
    Returns:
        Next node to execute.
    """
    input_type = state.get("input_type", "audio")
    
    # Text input skips STT
    if input_type == "text" or input_type == "streaming":
        if state.get("transcript") or state.get("streaming_transcript"):
            logger.info(f"Text/streaming input detected, routing to parse_intent")
            return "parse_intent"
    
    # Audio input goes through STT
    if input_type == "audio":
        logger.info("Audio input detected, routing to stt")
        return "stt"
    
    # Default to STT
    logger.info(f"Unknown input type '{input_type}', defaulting to stt")
    return "stt"


def should_continue_after_stt(
    state: TaskState,
) -> Literal["parse_intent", "error_handler"]:
    """
    Determine next step after speech-to-text processing.

    Args:
        state: Current task state.

    Returns:
        Next node to execute.
    """
    transcript = state.get("transcript") or state.get("streaming_transcript") or ""
    status = state.get("status", "")

    # Check for STT-specific errors via status field
    if status == "stt_failed":
        logger.info("STT failed, routing to error handler")
        return "error_handler"

    # Check if transcript is meaningful
    if not transcript or len(transcript.strip()) < 2:
        logger.info("Empty or invalid transcript, routing to error handler")
        return "error_handler"

    logger.info("STT successful, routing to intent parsing")
    return "parse_intent"


def should_continue_after_intent_parsing(
    state: TaskState,
) -> Literal[
    "perception",
    "speak",
    "error_handler",
    "coordinator",
    "web_search",
]:
    """
    Determine next step after intent parsing.

    UPDATED ROUTING (with Perception Controller):
    1. NO_UI actions (open_app, scroll, system toggles) → create_plan (skip perception)
       EXCEPT: Messaging actions when likely in app context → perception
    2. Screen reading requests → perception
    3. Conversational actions → speak
    4. UI actions requiring coordinates → perception
    5. Everything else → perception for UI analysis
    """
    intent = state.get("intent")
    # Check both transcript sources (streaming_transcript for WebSocket, transcript for text)
    transcript = (state.get("transcript") or state.get("streaming_transcript") or "").lower()
    status = state.get("status", "")

    # Check if sensitive action was blocked
    if status == "blocked":
        logger.warning("🚫 Sensitive action blocked, routing to speak node")
        return "speak"

    # Only check intent parsing-specific errors
    if status == "intent_failed" or not intent:
        logger.info("Intent parsing failed, routing to error handler")
        return "error_handler"

    action = intent.get("action", "").lower()
    confidence = intent.get("confidence", 0.0)

    if confidence < 0.3:
        logger.info(f"Low confidence ({confidence}), routing to error handler")
        return "error_handler"

    # If Commander explicitly flagged this for planning, honour it before any
    # conversational short-circuit.  This handles the common case where the LLM
    # returns action="general_interaction" + delegate_to_planner=true for complex
    # multi-step commands like "open YouTube, search X, and play the first video".
    # NOTE: the Commander nests this flag inside "parameters", so check both levels.
    _intent_params = intent.get("parameters") or {}
    if isinstance(_intent_params, list):
        _intent_params = {}
    if intent.get("delegate_to_planner") or _intent_params.get("delegate_to_planner"):
        logger.info(f"delegate_to_planner=true on '{action}' — routing to coordinator")
        return "coordinator"

    # Web search actions — route to dedicated node before any device routing.
    # Commander returns action="web_search" for queries like weather, news, facts.
    if action in WEB_SEARCH_ACTIONS:
        logger.info(f"Web search action '{action}' — routing to web_search node")
        return "web_search"

    # Conversational check FIRST — before any device routing.
    # Catches all aliases the Commander LLM may return (greet, hello, general_query, etc.)
    # Uses word-boundary regex to avoid false positives like "hi" inside "WhatsApp".
    if action in CONVERSATIONAL_ACTIONS or _CONVERSATIONAL_TRANSCRIPT_RE.search(transcript):
        logger.info(f"Conversational action '{action}' — routing to speak")
        return "speak"

    # Gate: low-confidence → full planner via coordinator
    # (general_interaction already caught above as conversational)
    if confidence < 0.6:
        if _SETTINGS.use_universal_agent:
            logger.info(f"Low confidence ({confidence}) — routing to coordinator for full planning")
            return "coordinator"

    # INTELLIGENT ROUTING: Check for complex parameters first
    intent_params = intent.get("parameters", {})
    has_complex_params = any(key in intent_params for key in ["goal", "target_section", "type", "content_type", "visual_reference"])

    # Check if UniversalAgent is enabled for complex goal routing
    settings = _SETTINGS
    use_universal_agent = settings.use_universal_agent
    
    # MULTI-STEP DETECTION: Commands with "and" typically need multiple actions
    # Examples: "open spotify and play liked songs", "go to settings and turn on wifi"
    multi_step_indicators = [" and ", " then ", " after that "]
    is_multi_step = any(indicator in transcript for indicator in multi_step_indicators)
    
    # Route multi-step commands to universal_agent (handles goal decomposition internally)
    if is_multi_step and use_universal_agent:
        logger.info(f"Multi-step command detected in transcript - routing to coordinator")
        return "coordinator"
    
    # NO_UI actions with complex params → route directly to universal_agent (skip perception)
    # This avoids capturing home screen before opening app
    if action in NO_UI_ACTIONS and has_complex_params and use_universal_agent:
        logger.info(f"NO_UI action '{action}' with complex goal {list(intent_params.keys())} - routing to coordinator (skip perception)")
        return "coordinator"
    
    # NO_UI actions without complex params → route to universal_agent
    if action in NO_UI_ACTIONS:
        logger.info(f"NO_UI action '{action}' - skipping perception, routing to coordinator")
        return "coordinator"
    
    # Special handling for messaging actions - check if we need UI
    messaging_actions = {"send_message", "send_whatsapp", "send_sms", "send_email"}
    if action in messaging_actions:
        # If transcript contains UI-related keywords, route to perception
        ui_keywords = ["tap", "click", "press", "button", "field", "on screen", "visible"]
        if any(keyword in transcript for keyword in ui_keywords):
            logger.info(f"Messaging action '{action}' with UI keywords - routing to perception")
            return "perception"
        # Otherwise, skip perception (will use deep link via coordinator)
        logger.info(f"Messaging action '{action}' - using deep link, routing to coordinator")
        return "coordinator"
    
    # UI actions with complex params → perception then universal_agent
    if has_complex_params:
        logger.info(f"Complex goal detected: '{action}' with params {list(intent_params.keys())} - routing to perception for Coordinator")
        return "perception"

    # Screen reading requests (what's on screen, describe screen, etc.)
    screen_reading_keywords = [
        "what's on", "what is on", "describe", "read screen", "show me what"
    ]
    if any(keyword in transcript for keyword in screen_reading_keywords):
        logger.info("Screen reading request detected, routing to perception")
        return "perception"

    # UI actions requiring coordinates must go through perception
    if action in COORDINATE_REQUIRING_ACTIONS:
        logger.info(f"Coordinate-requiring action '{action}' - routing to perception")
        return "perception"

    # Default: most actions benefit from perception data
    logger.info(f"Action '{action}' - routing to perception for UI context")
    return "perception"


def should_continue_after_perception(
    state: TaskState,
) -> Literal["create_plan", "speak", "error_handler", "coordinator"]:
    """
    Determine next step after perception.

    Args:
        state: Current task state with PerceptionBundle.

    Returns:
        Next node to execute.
    """
    perception_bundle = state.get("perception_bundle")
    status = state.get("status", "")
    intent = state.get("intent", {})
    action = intent.get("action", "").lower()
    session_id = state.get("session_id", "unknown")
    
    # Debug logging with session tracking
    logger.info(f"🔀 PERCEPTION→NEXT: session={session_id}, action={action}, status={status}")
    logger.debug(f"Edge after perception - bundle exists: {perception_bundle is not None}")

    # Only check perception-specific failures, NOT accumulated error_messages
    # The error_message field accumulates with a reducer, so old errors persist
    if status == "perception_failed":
        logger.info("Perception failed, routing to error handler")
        return "error_handler"

    # Check if perception bundle is available
    if not perception_bundle:
        logger.warning(f"No perception bundle available (status={status}), routing to error_handler")
        return "error_handler"

    # Screen reading requests should go directly to speak
    # The Screen Reader agent will be called in the speak node
    screen_reading_actions = ["read_screen", "describe", "describe_screen", "what_is_on_screen"]
    if action in screen_reading_actions:
        logger.info(f"🎯 Screen reading '{action}' → speak (session={session_id})")
        return "speak"

    # Check if UniversalAgent migration is enabled
    if _SETTINGS.use_universal_agent:
        # Route coordinate-requiring actions through UniversalAgent
        if action in COORDINATE_REQUIRING_ACTIONS:
            logger.info(f"🤖 Coordinator: routing '{action}' (session={session_id})")
            return "coordinator"
        
        # INTELLIGENT ROUTING: Actions with parameters = complex goals needing reasoning
        # Examples: "play liked songs" has type parameter, "send to John in WhatsApp" has app parameter
        intent_params = intent.get("parameters", {})
        has_complex_params = bool(intent_params and len(intent_params) > 0)
        
        if has_complex_params:
            logger.info(f"🤖 Coordinator: complex goal '{action}' with params {list(intent_params.keys())} (session={session_id})")
            return "coordinator"

    # After successful perception, route to Coordinator for all actions
    logger.info("Perception successful, routing to coordinator")
    return "coordinator"


def should_continue_after_speak(
    state: TaskState,
) -> Literal["__end__"]:
    """
    Determine next step after speaking.

    Always ends the graph execution.

    Args:
        state: Current task state.

    Returns:
        Always returns "__end__".
    """
    session_id = state.get("session_id", "unknown")
    status = state.get("status", "unknown")
    logger.info(f"🔚 SPEAK→END: session={session_id}, status={status}, routing to __end__")
    return "__end__"


def should_continue_after_error_handling(
    state: TaskState,
) -> Literal["perception", "speak", "__end__"]:
    """
    Determine next step after error handling.

    Args:
        state: Current task state.

    Returns:
        Next node to execute or end.
    """
    status = state.get("status", "")
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)
    intent = state.get("intent", {})
    action = intent.get("action", "").lower()

    # NO_UI actions should never retry with perception - it won't help
    if action in NO_UI_ACTIONS:
        logger.info(f"NO_UI action '{action}' - no point retrying perception, routing to speak")
        return "speak"

    # Only retry perception if status explicitly indicates perception failed
    # AND we haven't exceeded retry limit
    if retry_count < max_retries and status == "perception_failed":
        logger.info(f"Retrying with fresh perception (retry {retry_count + 1}/{max_retries})")
        return "perception"

    # Otherwise, report error and end
    logger.info("Error handling complete, routing to speak")
    return "speak"
