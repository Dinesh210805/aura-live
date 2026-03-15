"""
LangGraph conditional edges for the AURA backend.

This module defines the conditional logic that determines
the flow between nodes in the AURA task execution graph.
Uses fuzzy logic for intelligent agent routing.
"""

from typing import Literal

from config.action_types import (
    CONVERSATIONAL_ACTIONS,
    COORDINATE_REQUIRING_ACTIONS,
    NO_SCREEN_ACTIONS,
    NO_UI_ACTIONS,
    SIMPLE_DEVICE_ACTIONS,
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
    "parallel_processing",
    "analyze_ui",
    "create_plan",
    "execute",
    "speak",
    "error_handler",
    "coordinator",
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

    # Gate: low-confidence or general_interaction → always use full planner via coordinator
    # This prevents the single-subgoal shortcut from mishandling ambiguous/multi-step commands
    if confidence < 0.6 or action == "general_interaction":
        if _SETTINGS.use_universal_agent:
            logger.info(f"Low confidence ({confidence}) or general_interaction — routing to coordinator for full planning")
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
        # Otherwise, skip perception (will use deep link)
        logger.info(f"Messaging action '{action}' - using deep link, routing to create_plan")
        return "create_plan"
    
    # UI actions with complex params → perception then universal_agent
    if has_complex_params:
        logger.info(f"Complex goal detected: '{action}' with params {list(intent_params.keys())} - routing to perception for Coordinator")
        return "perception"

    # Check for conversational actions (greetings, help, etc.)
    if action in CONVERSATIONAL_ACTIONS or any(
        word in transcript for word in ["hello", "hi", "help", "what can you do"]
    ):
        logger.info("Conversational action detected, routing to speak")
        return "speak"

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


def should_continue_after_ui_analysis(
    state: TaskState,
) -> Literal["coordinator", "speak", "error_handler"]:
    """
    Determine next step after UI analysis (legacy node).

    Args:
        state: Current task state.

    Returns:
        Next node to execute.
    """
    status = state.get("status", "")

    # Only check UI-analysis-specific failures
    if status in ("ui_analysis_failed", "failed"):
        logger.info("UI analysis failed, routing to error handler")
        return "error_handler"

    logger.info("UI analysis successful, routing to coordinator")
    return "coordinator"


def route_after_parallel_processing(
    state: TaskState,
) -> Literal["coordinator", "speak", "error_handler"]:
    """
    Determine next step after parallel UI and validation processing.

    Args:
        state: Current task state.

    Returns:
        Next node to execute.
    """
    status = state.get("status", "")

    # Only check parallel-processing-specific failures
    if status in ("parallel_failed", "failed"):
        logger.info("Parallel processing failed, routing to error handler")
        return "error_handler"

    logger.info("Parallel processing successful, routing to coordinator")
    return "coordinator"


def should_continue_after_planning(
    state: TaskState,
) -> Literal["execute", "error_handler"]:
    """
    Determine next step after planning.

    Args:
        state: Current task state.

    Returns:
        Next node to execute.
    """
    plan = state.get("plan", [])
    status = state.get("status", "")

    # Only check planning-specific failures via status field
    if status == "planning_failed":
        logger.info("Planning failed, routing to error handler")
        return "error_handler"

    if not plan or len(plan) == 0:
        logger.info("No plan created, routing to error handler")
        return "error_handler"

    logger.info(f"Plan created with {len(plan)} steps, routing to execute")
    return "execute"


def should_continue_after_execution(
    state: TaskState,
) -> Literal["speak", "error_handler", "perception", "validate_outcome"]:
    """
    Determine next step after execution.
    
    UPDATED: Routes to validate_outcome for goal-driven execution when agent_state
    is present. Falls back to legacy behavior for simple commands.

    Args:
        state: Current task state.

    Returns:
        Next node to execute.
    """
    status = state.get("status", "")
    executed_steps = state.get("executed_steps", [])
    plan = state.get("plan", [])
    current_step = state.get("current_step", 0)
    agent_state = state.get("agent_state")
    
    # === GOAL-DRIVEN EXECUTION (NEW) ===
    # If agent_state exists and has a goal, route to validation
    if agent_state and hasattr(agent_state, 'goal') and agent_state.goal:
        logger.info("🎯 Goal-driven execution: routing to validate_outcome")
        return "validate_outcome"
    
    # === LEGACY MULTI-STEP HANDLING ===
    # If status is "multi_step_continue", we need to loop back for next step
    if status == "multi_step_continue":
        pending_steps = state.get("pending_steps", [])
        multi_step_index = state.get("multi_step_index", 0)
        multi_step_total = state.get("multi_step_total", 1)
        
        logger.info(f"🔗 MULTI-STEP: Step {multi_step_index}/{multi_step_total} complete, {len(pending_steps)} remaining")
        logger.info(f"   ↳ Routing to perception for fresh UI analysis")
        return "perception"  # Get fresh UI state for next step

    # Check for execution-specific failures via status field
    if status == "execution_failed":
        retry_count = state.get("retry_count", 0)
        max_retries = state.get("max_retries", 3)
        
        if retry_count < max_retries:
            logger.info(f"Execution error, retrying with fresh perception (retry {retry_count + 1}/{max_retries})")
            return "perception"  # Request fresh perception for retry
        else:
            logger.info("Max retries reached, routing to error handler")
            return "error_handler"

    # Check if all steps are complete
    if current_step >= len(plan):
        logger.info("All execution steps complete, routing to speak")
        return "speak"

    logger.info("Execution step complete, continuing to next step")
    return "speak"


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


def should_continue_after_validation(
    state: TaskState,
) -> Literal["next_subgoal", "retry_router", "speak"]:
    """
    Determine next step after validate_outcome node.
    
    Routes based on validation_routing field set by validate_outcome_node:
    - success: Advance to next subgoal
    - retry: Go to retry router to determine strategy
    - abort: Report failure to user
    
    Args:
        state: Current task state with validation_result.
        
    Returns:
        Next node to execute.
    """
    validation_routing = state.get("validation_routing", "success")
    validation_result = state.get("validation_result", {})
    
    logger.info(f"🔍 VALIDATION routing: {validation_routing}")
    
    if validation_routing == "success":
        logger.info("Action validated successfully, advancing to next subgoal")
        return "next_subgoal"
    
    if validation_routing == "retry":
        logger.info(f"Action failed validation: {validation_result.get('reason', 'unknown')}")
        return "retry_router"
    
    if validation_routing == "abort":
        abort_reason = validation_result.get("abort_reason", "unknown")
        logger.warning(f"Action aborted: {abort_reason}")
        return "speak"
    
    # Default to success for backward compatibility
    logger.info("Unknown validation routing, defaulting to next_subgoal")
    return "next_subgoal"


def should_continue_after_retry_router(
    state: TaskState,
) -> Literal["perception", "execute", "speak"]:
    """
    Determine next step after retry_router node.
    
    Routes based on retry_action type:
    - repeat: Execute same action again
    - alternate_selector/scroll_then_retry/vision_fallback: Get fresh perception
    - abort: Report failure to user
    
    Args:
        state: Current task state with retry_action.
        
    Returns:
        Next node to execute.
    """
    retry_action = state.get("retry_action", {})
    action_type = retry_action.get("type", "repeat")
    
    logger.info(f"🔄 RETRY routing: action_type={action_type}")
    
    if action_type == "abort":
        logger.warning("All retry strategies exhausted, reporting failure")
        return "speak"
    
    if action_type == "repeat":
        logger.info("Retrying same action immediately")
        return "execute"
    
    # Strategies that need fresh perception
    if action_type in ("alternate_selector", "scroll_then_retry", "vision_fallback"):
        logger.info(f"Strategy '{action_type}' requires fresh perception")
        return "perception"
    
    # Default to perception for safety
    logger.info("Unknown retry action, defaulting to perception")
    return "perception"


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
