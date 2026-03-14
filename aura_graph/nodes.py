"""
LangGraph nodes for the AURA backend.

This module defines the individual processing nodes that make up
the AURA task execution graph. Each node represents a distinct
step in the user command processing pipeline.
"""

import base64
import time
from typing import TYPE_CHECKING, Any, Dict, List

from config.action_types import (
    COORDINATE_REQUIRING_ACTIONS,
    NO_SCREEN_ACTIONS,
    NO_UI_ACTIONS,
)
from config.settings import Settings
from services.llm import LLMService
from services.real_accessibility import RealAccessibilityService
from services.real_device_executor import RealDeviceExecutorService
from services.stt import STTService
from services.tts import TTSService
from services.vlm import VLMService
from utils.exceptions import AgentExecutionError, ModelProviderError
from utils.logger import get_logger
from utils.types import IntentObject

from .state import TaskState

# TYPE_CHECKING prevents circular imports while preserving type hints
if TYPE_CHECKING:
    from agents.commander import CommanderAgent
    from agents.responder import ResponderAgent
    from agents.visual_locator import ScreenVLM
    from agents.validator import ValidatorAgent

INTENT_OBJECT_MODEL = IntentObject

logger = get_logger(__name__)


def add_workflow_step(
    state: TaskState,
    node_name: str,
    status: str,
    description: str,
    output: Any = None,
    error: str = None,
    details: Dict[str, Any] = None,
):
    """
    Add a workflow step to track execution progress.

    Args:
        state: Current task state.
        node_name: Name of the current node.
        status: Status of the step (running, completed, error).
        description: Description of what this step does.
        output: Optional output from the step.
        error: Optional error message.
        details: Optional additional details.
    """
    if state.get("track_workflow") and state.get("workflow_steps") is not None:
        step = {
            "node": node_name,
            "status": status,
            "description": description,
            "timestamp": time.time(),
            "execution_time": None,
        }

        if output is not None:
            step["output"] = (
                str(output) if not isinstance(output, (dict, list)) else output
            )

        if error:
            step["error"] = error

        if details:
            step["details"] = details

        state["workflow_steps"].append(step)


def track_agent_usage(state: TaskState, agent_name: str):
    """
    Track which agents are being used for this task.

    Args:
        state: Current task state.
        agent_name: Name of the agent being used.
    """
    if "used_agents" not in state:
        state["used_agents"] = []

    if agent_name not in state["used_agents"]:
        state["used_agents"].append(agent_name)
        logger.info(f"Agent {agent_name} added to execution workflow")


def update_workflow_step(
    state: TaskState,
    node_name: str,
    status: str,
    description: str = None,
    output: Any = None,
    error: str = None,
    execution_time: float = None,
    details: Dict[str, Any] = None,
):
    """
    Update the last workflow step for a node.

    Args:
        state: Current task state.
        node_name: Name of the node to update.
        status: New status.
        description: Updated description.
        output: Step output.
        error: Error message if any.
        execution_time: Execution time for the step.
        details: Additional details to include.
    """
    if state.get("track_workflow") and state.get("workflow_steps") is not None:
        # Find the most recent step for this node
        for step in reversed(state["workflow_steps"]):
            if step["node"] == node_name:
                step["status"] = status
                if description:
                    step["description"] = description
                if output is not None:
                    step["output"] = (
                        str(output) if not isinstance(output, (dict, list)) else output
                    )
                if error:
                    step["error"] = error
                if execution_time is not None:
                    step["execution_time"] = execution_time
                if details:
                    step["details"] = details
                step["timestamp"] = time.time()
                break


# Global service instances (will be initialized in graph.py)
settings: Settings = None
stt_service: STTService = None
llm_service: LLMService = None
vlm_service: VLMService = None
tts_service: TTSService = None
accessibility_service: RealAccessibilityService = None
device_executor_service: RealDeviceExecutorService = None
commander_agent: Any = None  # CommanderAgent initialized at runtime
responder_agent: Any = None  # ResponderAgent initialized at runtime
screen_vlm_agent: Any = None  # ScreenVLM initialized at runtime
validator_agent: Any = None  # ValidatorAgent initialized at runtime


def stt_node(state: TaskState) -> Dict[str, Any]:
    """
    Speech-to-Text node: Convert raw audio to text transcript.

    Supports both batch processing (raw_audio) and streaming transcripts.

    Args:
        state: Current task state containing raw_audio or streaming_transcript.

    Returns:
        State update with transcript field.
    """
    try:
        logger.info("STT node: Converting audio to text")

        # Check if we have a streaming transcript (WebSocket case)
        streaming_transcript = state.get("streaming_transcript", "").strip()
        if streaming_transcript:
            logger.info(
                f"STT node: Using streaming transcript: {streaming_transcript[:100]}..."
            )
            add_workflow_step(
                state,
                "STT",
                "completed",
                "Used streaming transcript from WebSocket",
                output={"transcript": streaming_transcript[:100] + "..."},
            )
            return {
                "transcript": streaming_transcript,
                "status": "transcribed",
                "processing_method": "streaming",
            }

        # Check if we already have a transcript (text input case)
        existing_transcript = state.get("transcript", "").strip()
        if existing_transcript:
            logger.info(
                f"STT node: Transcript already available, passing through: {existing_transcript[:100]}..."
            )
            add_workflow_step(
                state,
                "STT",
                "completed",
                "Used existing transcript",
                output={"transcript": existing_transcript[:100] + "..."},
            )
            return {
                "transcript": existing_transcript,
                "status": "transcribed",
                "processing_method": "direct",
            }

        # Extract audio data from state for batch processing
        raw_audio = state.get("raw_audio")
        if not raw_audio:
            raise ModelProviderError(
                "No audio data or transcript provided for transcription",
                provider="stt",
                error_code="MISSING_INPUT_DATA",
            )

        add_workflow_step(state, "STT", "running", "Processing audio with STT service")

        # Extract language hint from multiple sources (priority order)
        # 1. Explicit language field in state
        # 2. stt_language field in state
        # 3. Language from context dict
        # 4. Default STT language from settings
        # 5. None (auto-detect)
        context_data = (
            state.get("context") if isinstance(state.get("context"), dict) else {}
        )
        language_hint = (
            state.get("language")
            or state.get("stt_language")
            or context_data.get("language")
            or context_data.get("stt_language")
            or settings.default_stt_language
        )

        if language_hint:
            logger.info(f"STT using language hint: {language_hint}")
        else:
            logger.info(
                "STT using automatic language detection (supports Tamil, English, Hindi, etc.)"
            )

        # Transcribe audio to text (batch mode)
        transcript = stt_service.transcribe(raw_audio, language=language_hint)

        # Update task status
        status_update = {
            "transcript": transcript,
            "status": "transcribed",
            "processing_method": "batch",
        }

        if not state.get("start_time"):
            status_update["start_time"] = time.time()

        add_workflow_step(
            state,
            "STT",
            "completed",
            "Audio transcribed successfully",
            output={"transcript": transcript[:100] + "...", "method": "batch"},
        )

        logger.info(f"STT completed: {transcript[:100]}...")
        return status_update

    except Exception as e:
        logger.error(f"STT node failed: {e}")
        add_workflow_step(state, "STT", "error", "STT processing failed", error=str(e))
        return {
            "transcript": "",
            "error_message": f"Speech transcription failed: {str(e)}",
            "status": "stt_failed",
        }


def parse_intent_node(state: TaskState) -> Dict[str, Any]:
    """
    Parse Intent node: Extract structured intent from transcript using Commander agent.

    Args:
        state: Current task state containing transcript.

    Returns:
        State update with intent field.
    """
    start_time = time.time()
    node_name = "Parse Intent"

    try:
        # Check if intent has already been parsed to prevent duplicate execution
        existing_intent = state.get("intent")
        if existing_intent and existing_intent.get("confidence", 0) > 0.8:
            logger.info(
                "Parse Intent node: High-confidence intent already exists, skipping re-parse"
            )
            return {"status": "intent_already_parsed"}

        logger.info("Parse Intent node: Analyzing user intent")
        add_workflow_step(
            state, node_name, "running", "Analyzing user intent with Commander agent"
        )

        # Track that the Commander agent is being used
        track_agent_usage(state, "commander")

        # Extract transcript from state (check both sources)
        transcript = state.get("transcript") or state.get("streaming_transcript")
        if not transcript:
            error_msg = "No transcript available for intent parsing"
            update_workflow_step(state, node_name, "error", error=error_msg)
            raise AgentExecutionError(
                error_msg, agent_name="Commander", error_code="MISSING_TRANSCRIPT"
            )

        # === ENTITY RESOLUTION: Resolve pronouns before parsing ===
        session_id = state.get("session_id", "default")
        commander_context = None
        try:
            from services.conversation_session import get_session_manager
            from services.entity_resolver import get_entity_resolver

            session = get_session_manager().get_session(session_id)
            resolver = get_entity_resolver()

            # Get full context for resolution
            full_context = session.get_full_context()

            # Build conversation context for Commander (app memory)
            if full_context.current_app or full_context.last_action:
                commander_context = {
                    "current_app": full_context.current_app,
                    "last_action": full_context.last_action,
                    "last_target": full_context.last_target,
                }

            # Resolve pronouns like 'it', 'that', 'there'
            if resolver.needs_resolution(transcript):
                resolved_transcript = resolver.resolve(transcript, full_context)
                logger.info(f"ðŸ”— Entity resolution: '{transcript}' â†’ '{resolved_transcript}'")
                transcript = resolved_transcript
            else:
                logger.debug("No entity resolution needed")

        except Exception as resolve_error:
            logger.warning(f"Entity resolution skipped: {resolve_error}")
            # Continue with original transcript if resolution fails

        # Parse intent using Commander agent with conversation context
        intent_obj = commander_agent.parse_intent(transcript, context=commander_context)

        # Validate the parsed intent
        if not commander_agent.validate_intent(intent_obj):
            logger.warning("Parsed intent failed validation, proceeding with caution")

        # Convert to dictionary for state storage
        intent_dict = intent_obj.dict()

        # === PHASE 9: INTENT NORMALIZATION ===
        # Map semantic intent actions to canonical executable actions
        # This ensures semantic variants like "open_settings" â†’ canonical "open_app"
        # Unknown actions gracefully fallback to general_interaction
        from services.intent_normalizer import normalize_intent_action

        intent_dict = normalize_intent_action(intent_dict)
        logger.info(
            f"Normalized intent: action={intent_dict.get('action')}, "
            f"recipient={intent_dict.get('recipient')}"
        )

        execution_time = time.time() - start_time

        update_workflow_step(
            state,
            node_name,
            "completed",
            f"Intent parsed & normalized: {intent_dict.get('action')} -> {intent_dict.get('recipient')}",
            execution_time=execution_time,
        )

        logger.info(
            f"â†’ Intent parsed & normalized: {intent_dict.get('action')} -> {intent_dict.get('recipient')}"
        )
        
        # === MULTI-STEP DETECTION ===
        # Check if intent has additional steps in parameters
        result = {"intent": intent_dict, "status": "intent_parsed"}
        
        parameters = intent_dict.get("parameters", {})
        pending_steps = parameters.get("steps", [])
        
        if pending_steps:
            logger.info(f"ðŸ”— Multi-step command detected: {len(pending_steps)} additional step(s)")
            result["pending_steps"] = pending_steps
            result["multi_step_index"] = 0
            result["multi_step_total"] = 1 + len(pending_steps)
            result["multi_step_results"] = []
            result["original_intent"] = intent_dict.copy()
            
            for i, step in enumerate(pending_steps, 1):
                logger.info(f"   Step {i}: {step.get('action', 'unknown')} â†’ {step.get('target', step.get('direction', 'N/A'))}")
        
        return result

    except Exception as e:
        execution_time = time.time() - start_time
        error_msg = f"Intent parsing failed: {str(e)}"
        update_workflow_step(
            state, node_name, "error", error=error_msg, execution_time=execution_time
        )

        logger.error(f"Parse Intent node failed: {e}", exc_info=True)
        logger.error(f"  Transcript: {state.get('transcript', 'N/A')[:100]}...")
        logger.error(f"  Input type: {state.get('input_type', 'N/A')}")
        return {
            "intent": {
                "action": "unknown",
                "recipient": None,
                "content": state.get("transcript", ""),
                "confidence": 0.0,
            },
            "error_message": error_msg,
            "status": "intent_failed",
        }


def _is_screen_description_intent(intent: Dict[str, Any], transcript: str) -> bool:
    """Check if the intent is asking for a screen description."""
    if not intent:
        return False

    action = intent.get("action", "")
    action = action.lower() if action else ""

    content = intent.get("content", "")
    content = content.lower() if content else ""

    transcript_lower = transcript.lower() if transcript else ""

    # Actions that indicate screen description
    description_actions = [
        "describe",
        "screen",
        "read",
        "read_screen",
        "analyze",
        "see",
        "view",
        "look",
    ]

    # Keywords that indicate screen description
    description_keywords = [
        "what's on",
        "what is on",
        "whats on",
        "describe",
        "read screen",
        "read the screen",
        "read my screen",
        "what do you see",
        "what can you see",
        "tell me what",
        "show me what",
        "current screen",
        "my screen",
        "on my screen",
        "on screen",
        "what's visible",
        "what is visible",
        "analyze screen",
        "screen content",
    ]

    # Check action - exact match for read_screen
    if action == "read_screen":
        return True

    # Check action - partial match
    if any(act in action for act in description_actions):
        return True

    # Check content
    if any(kw in content for kw in description_keywords):
        return True

    # Check transcript
    if any(kw in transcript_lower for kw in description_keywords):
        return True

    return False


def _generate_screen_description(
    screenshot_b64: str, ui_elements: list, vlm_service: VLMService
) -> str:
    """Generate a natural language description of the screen using VLM."""
    try:
        # Build element summary for context
        element_summary = []
        for elem in ui_elements[:15]:  # Limit to top 15 elements
            text = elem.text if hasattr(elem, "text") else elem.get("text", "")
            class_name = (
                elem.className
                if hasattr(elem, "className")
                else elem.get("class_name", "")
            )
            content_desc = (
                elem.contentDescription
                if hasattr(elem, "contentDescription")
                else elem.get("content_desc", "")
            )

            if text or content_desc:
                desc = text or content_desc
                element_summary.append(f"- {class_name}: '{desc}'")

        elements_text = (
            "\n".join(element_summary)
            if element_summary
            else "No text elements detected"
        )

        prompt = f"""You are a helpful assistant describing a mobile phone screen to a user who cannot see it.

DETECTED UI ELEMENTS:
{elements_text}

Please provide a concise, natural description of what's on this screen. Focus on:
1. What app or screen appears to be showing
2. Key visible text and buttons
3. Main content or actions available

Keep your response to 2-3 sentences, conversational and helpful.
Start with "I can see..." or "You're looking at..." or similar natural phrasing."""

        # If we have a REAL screenshot (not a tiny placeholder), use VLM to analyze it
        # A real screenshot should be at least 1KB (1000 bytes base64)
        if screenshot_b64 and len(screenshot_b64) > 1000:
            logger.info(
                f"Using VLM to describe screen with screenshot ({len(screenshot_b64)} bytes)"
            )
            description = vlm_service.analyze_image(screenshot_b64, prompt, agent="ScreenDescriber")
            return description.strip()
        elif screenshot_b64 and len(screenshot_b64) > 100:
            # This is likely a placeholder/demo image - don't send to VLM as it will hallucinate
            logger.warning(
                f"Screenshot too small ({len(screenshot_b64)} bytes) - likely placeholder, skipping VLM"
            )
        else:
            # No screenshot, generate description from UI elements only
            logger.info(
                "Generating screen description from UI elements only (no screenshot)"
            )
            if not element_summary:
                return "I can see the screen but couldn't detect any readable text or elements. The screen might be showing an image or video content."

            # Text-based description from UI elements only - be honest about limitations
            logger.info(
                "Generating description from UI elements only (no valid screenshot)"
            )

            # Filter out demo/placeholder elements (check for known demo patterns)
            demo_indicators = [
                "com.android.launcher3",
                "demo",
                "test",
                "placeholder",
                "aura.placeholder",
            ]
            is_demo_data = any(
                any(indicator in str(elem).lower() for indicator in demo_indicators)
                for elem in ui_elements[:5]
            )

            if is_demo_data or not element_summary:
                return "I'm unable to capture your actual screen right now. Please make sure the AURA app on your phone is connected and screen capture is enabled."

            # Real UI elements but no screenshot
            visible_texts = [e.split("'")[1] for e in element_summary if "'" in e][:5]
            if visible_texts:
                return f"I can detect {len(ui_elements)} elements on screen. Some visible text: {', '.join(visible_texts[:3])}. However, I couldn't capture the full screen image for detailed analysis."
            else:
                return f"I can detect {len(ui_elements)} interactive elements on screen, but couldn't capture the full screen image."

    except Exception as e:
        logger.error(f"Failed to generate screen description: {e}")
        return f"I can see the screen has {len(ui_elements) if ui_elements else 'some'} elements, but I couldn't generate a detailed description."


def analyze_ui_node(state: TaskState) -> Dict[str, Any]:
    """
    Analyze UI node: Capture UI data and optionally generate screen descriptions.

    Args:
        state: Current task state.

    Returns:
        State update with UI data and optional screen description.
    """
    start_time = time.time()
    node_name = "Analyze UI"

    try:
        logger.info("Analyze UI node: Analyzing real device UI")
        add_workflow_step(
            state,
            node_name,
            "running",
            "Analyzing real device UI and capturing screenshot",
        )

        # Check if this is a screen description request
        intent = state.get("intent", {})
        transcript = state.get("transcript", "")
        is_description_request = _is_screen_description_intent(intent, transcript)

        # Track that the Navigator agent is being used
        track_agent_usage(state, "navigator")

        # Use real accessibility service for UI analysis
        import asyncio

        from services.real_accessibility import real_accessibility_service

        # Note: This legacy node has been replaced by perception_node.
        # Legacy automatic screenshot capture and UI tree retrieval removed.
        # Perception must be explicitly requested via the Perception Controller.
        # This node now fails loudly if called, directing users to use perception_node instead.
        
        # Fail loudly if perception data is not available
        raise AgentExecutionError(
            "UI perception data not available - Perception Controller must provide it",
            agent_name="AnalyzeUI",
            error_code="MISSING_PERCEPTION_DATA",
        )

    except Exception as e:
        execution_time = time.time() - start_time
        error_details = {
            "error_type": type(e).__name__,
            "error_message": str(e),
            "execution_time": execution_time,
        }

        update_workflow_step(
            state,
            node_name,
            "failed",
            f"UI analysis failed: {str(e)}",
            output=error_details,
            execution_time=execution_time,
        )

        logger.error(f"Analyze UI node failed: {e}")
        return {
            "ui_screenshot": None,
            "ui_tree": None,
            "ui_elements": [],
            "error_message": f"UI analysis failed: {str(e)}",
            "status": "failed",
        }


def plan_node(state: TaskState) -> Dict[str, Any]:
    """
    Plan node: Create execution plan using Navigator agent with PerceptionBundle.

    Args:
        state: Current task state with intent and PerceptionBundle.

    Returns:
        State update with execution plan.
    """
    start_time = time.time()
    node_name = "Plan Actions"

    try:
        logger.info("Plan node: Creating execution plan")
        add_workflow_step(
            state, node_name, "running", "Creating execution plan from PerceptionBundle"
        )

        # Extract required data from state
        intent_dict = state.get("intent")

        if not intent_dict:
            raise AgentExecutionError(
                "No intent available for planning",
                agent_name="Navigator",
                error_code="MISSING_INTENT",
            )

        # Convert intent dict to object
        intent_obj = INTENT_OBJECT_MODEL(**intent_dict)

        # Check if this is a NO_UI action first (doesn't need perception)
        from config.action_types import NO_UI_ACTIONS
        action = intent_obj.action.lower()
        
        perception_bundle = None
        if action in NO_UI_ACTIONS:
            logger.info(f"NO_UI action '{action}' - creating plan without perception bundle")
        else:
            # Extract PerceptionBundle from state
            perception_bundle_data = state.get("perception_bundle")
            
            if perception_bundle_data:
                from perception.models import PerceptionBundle
                try:
                    # Handle both object and dict formats
                    if isinstance(perception_bundle_data, PerceptionBundle):
                        perception_bundle = perception_bundle_data
                    elif isinstance(perception_bundle_data, dict):
                        perception_bundle = PerceptionBundle(**perception_bundle_data)
                    else:
                        logger.warning(f"Unknown perception_bundle type: {type(perception_bundle_data)}")
                    
                    if perception_bundle:
                        modality_str = perception_bundle.modality.value if hasattr(perception_bundle.modality, 'value') else str(perception_bundle.modality)
                        logger.info(
                            f"Using PerceptionBundle: modality={modality_str}, "
                            f"snapshot_id={perception_bundle.snapshot_id}"
                        )
                except Exception as e:
                    logger.warning(f"Failed to parse PerceptionBundle: {e}, proceeding without it")
        
        # Navigator agent has been removed - all actions now route through UniversalAgent
        # This code path should not be reached in normal operation
        logger.warning("plan_node is deprecated - all actions should route through UniversalAgent")
        return {
            "plan": [],
            "current_step": 0,
            "status": "planning_failed",
            "error": "Navigator agent removed - all actions should route through UniversalAgent",
        }

    except Exception as e:
        execution_time = time.time() - start_time
        update_workflow_step(
            state,
            node_name,
            "failed",
            f"Planning failed: {str(e)}",
            execution_time=execution_time,
        )

        logger.error(f"Plan node failed: {e}")
        return {
            "plan": [],
            "error_message": f"Planning failed: {str(e)}",
            "status": "planning_failed",
        }


async def execute_node(state: TaskState) -> Dict[str, Any]:
    """
    Execute node: Generate instruction plan for frontend execution.

    This node now generates structured instruction plans instead of direct execution:
    - Intent-based instruction generation
    - Step-by-step action planning
    - Confidence scoring and validation
    - Structured output for frontend consumption

    Args:
        state: Current task state with execution plan.

    Returns:
        State update with instruction plan for frontend execution.
    """
    start_time = time.time()
    node_name = "Generate Instructions"

    try:
        logger.info("Execute node: Generating instruction plan for frontend")
        add_workflow_step(
            state,
            node_name,
            "running",
            "Generating instruction plan for frontend execution",
        )

        # Track that the instruction generator is being used
        track_agent_usage(state, "instruction_generator")

        # Extract execution data from state
        intent_dict = state.get("intent")
        action_plan = state.get("plan", [])

        if not intent_dict:
            raise AgentExecutionError(
                "No intent object available for execution",
                agent_name="AutomationOrchestrator",
                error_code="MISSING_INTENT",
            )

        # Convert intent dictionary to IntentObject for action check
        intent_obj_temp = (
            INTENT_OBJECT_MODEL(**intent_dict)
            if isinstance(intent_dict, dict)
            else intent_dict
        )
        action = intent_obj_temp.action.lower() if intent_obj_temp.action else ""

        # Phase 2: Only allow plan synthesis for NO_UI_ACTIONS and NO_SCREEN_ACTIONS
        # Coordinate-requiring actions MUST have a plan from Navigator
        if not action_plan:
            # Check if this action requires coordinates (must have come from Navigator)
            if action in COORDINATE_REQUIRING_ACTIONS:
                raise AgentExecutionError(
                    f"Action '{action}' requires coordinates but no plan was provided. "
                    "Navigator must provide coordinates for tap/click/swipe/long_press actions.",
                    agent_name="AutomationOrchestrator",
                    error_code="MISSING_COORDINATES",
                )

            # For NO_UI_ACTIONS and NO_SCREEN_ACTIONS, generate simple plan from intent
            if action in NO_UI_ACTIONS or action in NO_SCREEN_ACTIONS:
                logger.info(f"No-UI/No-Screen action '{action}': generating simple plan from intent")
                
                # Build simple plan step
                plan_step = {"action": action}
                if intent_obj_temp.recipient:
                    plan_step["target"] = intent_obj_temp.recipient
                if intent_obj_temp.content:
                    plan_step["content"] = intent_obj_temp.content
                if intent_obj_temp.parameters:
                    plan_step["parameters"] = intent_obj_temp.parameters
                action_plan = [plan_step]
                state["plan"] = action_plan
                logger.info(f"Generated simple plan: {action_plan}")
            else:
                # Unknown action without plan - fail explicitly
                raise AgentExecutionError(
                    f"Action '{action}' has no execution plan. "
                    "Complex actions must go through Navigator for planning.",
                    agent_name="AutomationOrchestrator",
                    error_code="NO_PLAN",
                )

        # Convert intent dictionary to IntentObject
        if isinstance(intent_dict, dict):
            intent_obj = INTENT_OBJECT_MODEL(**intent_dict)
        else:
            intent_obj = intent_dict

        # Execute action plan on real device
        logger.info(f"Executing automation for: {intent_obj.action}")

        from services.real_device_executor import real_device_executor

        # Execute the action plan
        execution_results = await real_device_executor.execute_action_plan(action_plan)

        # Process results
        execution_successful = execution_results.get("success", False)
        execution_steps = execution_results.get("execution_steps", [])
        strategy_used = execution_results.get("strategy_used", "real_device_automation")
        error_message = execution_results.get("error_message")
        errors = execution_results.get("errors", [])

        if errors:
            error_message = "; ".join(errors)

        execution_time = time.time() - start_time

        # Prepare state update
        update_data = {
            "executed_steps": execution_steps,
            "current_step": len(execution_steps),
            "status": "completed" if execution_successful else "failed",
            "automation_strategy_used": strategy_used,
        }

        if not execution_successful:
            update_data["error_message"] = error_message or "Execution failed"

            update_workflow_step(
                state,
                node_name,
                "completed_with_errors",
                f"Completed with errors using {strategy_used}",
                execution_time=execution_time,
            )
        else:
            update_workflow_step(
                state,
                node_name,
                "completed",
                f"Executed successfully using {strategy_used}",
                execution_time=execution_time,
            )

        logger.info(
            f"Execution completed: success={execution_successful}, strategy={strategy_used}"
        )

        # === PERCEPTION BUNDLE INVALIDATION ===
        # UI actions change the screen state - invalidate perception bundle
        if execution_successful and action not in NO_UI_ACTIONS and action not in NO_SCREEN_ACTIONS:
            try:
                from services.perception_controller import get_perception_controller
                
                controller = get_perception_controller()
                controller.invalidate_bundle(
                    reason=f"UI action executed: {action} on {intent_obj.recipient or 'screen'}"
                )
                logger.info(f"ðŸ”„ Perception bundle invalidated after {action}")
            except Exception as inv_error:
                logger.warning(f"Bundle invalidation failed: {inv_error}")

        # === UPDATE DEVICE STATES FOR TOGGLE ACTIONS ===
        if execution_successful and intent_obj:
            try:
                from services.conversation_session import get_session_manager

                session_id = state.get("session_id", "default")
                session = get_session_manager().get_session(session_id)
                action = intent_obj.action.lower()

                # Track device state changes
                if "wifi" in action:
                    state_value = "on" in action or action == "toggle_wifi"
                    session.update_device_state("wifi", state_value)
                    logger.debug(f"Device state: wifi={state_value}")

                elif "bluetooth" in action:
                    state_value = "on" in action or action == "toggle_bluetooth"
                    session.update_device_state("bluetooth", state_value)
                    logger.debug(f"Device state: bluetooth={state_value}")

                elif "torch" in action or "flashlight" in action:
                    state_value = "on" in action
                    session.update_device_state("torch", state_value)
                    logger.debug(f"Device state: torch={state_value}")

            except Exception as state_error:
                logger.warning(f"Device state tracking failed: {state_error}")

        # === MULTI-STEP EXECUTION HANDLING ===
        # Check if there are pending steps after successful primary action
        pending_steps = state.get("pending_steps", [])
        multi_step_index = state.get("multi_step_index", 0)
        multi_step_total = state.get("multi_step_total", 1)
        multi_step_results = state.get("multi_step_results", [])
        
        if execution_successful and pending_steps:
            # Record result of current step
            step_result = {
                "step_index": multi_step_index,
                "action": action,
                "success": True,
                "strategy": strategy_used,
            }
            multi_step_results.append(step_result)
            
            # Get next step from pending
            next_step = pending_steps[0]
            remaining_steps = pending_steps[1:]
            
            logger.info(f"ðŸ”— MULTI-STEP: Completed step {multi_step_index + 1}/{multi_step_total}")
            logger.info(f"   Next step: {next_step.get('action', 'unknown')} â†’ {next_step.get('target', next_step.get('direction', 'N/A'))}")
            
            # Build new intent from the next step
            next_action = next_step.get("action", "tap")
            next_target = next_step.get("target")
            next_direction = next_step.get("direction")
            next_content = next_step.get("content")
            
            next_intent = {
                "action": next_action,
                "recipient": next_target,
                "content": next_content,
                "parameters": {k: v for k, v in next_step.items() if k not in ["action", "target", "content"]},
                "confidence": 0.9,
            }
            
            # Handle direction for scroll actions
            if next_direction:
                next_intent["parameters"]["direction"] = next_direction
            
            # Update state for next iteration
            update_data["intent"] = next_intent
            update_data["pending_steps"] = remaining_steps
            update_data["multi_step_index"] = multi_step_index + 1
            update_data["multi_step_results"] = multi_step_results
            update_data["plan"] = []  # Clear plan for fresh planning
            update_data["perception_bundle"] = None  # Force fresh perception
            update_data["status"] = "multi_step_continue"  # Signal to continue
            
            logger.info(f"   Remaining steps: {len(remaining_steps)}")
            
            # Add wait time for UI to settle after action
            import asyncio
            await asyncio.sleep(1.5)  # Wait for app/UI to load
        
        elif execution_successful and multi_step_total > 1:
            # Final step of multi-step command completed
            step_result = {
                "step_index": multi_step_index,
                "action": action,
                "success": True,
                "strategy": strategy_used,
            }
            multi_step_results.append(step_result)
            
            logger.info(f"âœ… MULTI-STEP COMPLETE: All {multi_step_total} steps executed successfully")
            update_data["multi_step_results"] = multi_step_results
            update_data["status"] = "completed"

        # === GENERATE FEEDBACK MESSAGE for speak_node ===
        # Create a helpful response so speak_node doesn't regenerate via LLM with wrong context
        if execution_successful:
            transcript = state.get("transcript") or state.get("streaming_transcript") or ""
            # Build a clear success message based on what was done
            step_count = len(execution_steps)
            if step_count == 1 and execution_steps:
                first_step = execution_steps[0]
                action_desc = first_step.get("action", "action")
                update_data["feedback_message"] = f"Done! I completed the {action_desc}."
            elif step_count > 1:
                update_data["feedback_message"] = f"Done! I completed your request in {step_count} steps."
            else:
                update_data["feedback_message"] = "Done!"
            
            # Store goal summary for multi-step awareness
            update_data["goal_summary"] = transcript
        
        return update_data

    except Exception as e:
        execution_time = time.time() - start_time
        {
            "error_type": type(e).__name__,
            "error_message": str(e),
            "execution_time": execution_time,
            "available_data": {
                "has_intent": bool(state.get("intent")),
                "has_plan": bool(state.get("plan")),
                "plan_length": len(state.get("plan", [])),
                "orchestrator_available": device_executor_service is not None,
            },
        }

        update_workflow_step(
            state,
            node_name,
            "failed",
            f"Execution failed: {str(e)}",
            execution_time=execution_time,
        )

        logger.error(f"Execute node failed: {e}")
        return {
            "executed_steps": [],
            "error_message": f"Execution failed: {str(e)}",
            "status": "execution_failed",
        }


def speak_node(state: TaskState) -> Dict[str, Any]:
    """
    Speak node: Generate and deliver spoken feedback using Responder agent.
    Also handles screen reading requests using Screen Reader agent.

    Args:
        state: Current task state with execution results.

    Returns:
        State update with feedback information.
    """
    start_time = time.time()
    node_name = "Generate Response"

    try:
        logger.info("Speak node: Generating spoken feedback")
        add_workflow_step(
            state,
            node_name,
            "running",
            "Generating spoken feedback based on execution results",
        )

        # Extract data for feedback generation
        intent_dict = state.get("intent")
        status = state.get("status", "unknown")
        executed_steps_data = state.get("executed_steps", [])
        error_message = state.get("error_message")
        feedback_message = state.get(
            "feedback_message"
        )  # Check if error handler already set a message

        # Extract conversation context (NEW)
        conversation_turn = state.get("conversation_turn", 0)
        has_introduced = state.get("has_introduced", False)
        is_follow_up = state.get("is_follow_up", False)
        session_id = state.get("session_id")

        # === HANDLE SCREEN READING REQUESTS ===
        # If action is read_screen and we have a perception bundle, use Screen Reader
        if intent_dict and intent_dict.get("action", "").lower() in ["read_screen", "describe", "describe_screen", "what_is_on_screen"]:
            logger.info(f"ðŸ” SCREEN READING PATH: session={session_id}, action={intent_dict.get('action')}")
            perception_bundle = state.get("perception_bundle")
            if perception_bundle and screen_vlm_agent:
                try:
                    logger.info("Screen reading request detected, using ScreenVLM agent")
                    track_agent_usage(state, "screen_vlm")
                    
                    # Convert perception_bundle dict to PerceptionBundle object
                    from perception.models import PerceptionBundle
                    if isinstance(perception_bundle, dict):
                        bundle = PerceptionBundle(**perception_bundle)
                    else:
                        bundle = perception_bundle
                    
                    # Call screen reader asynchronously
                    import asyncio
                    description = asyncio.run(screen_vlm_agent.describe_screen(bundle, focus="general"))
                    feedback_message = description
                    logger.info(f"Screen description generated: {description[:100]}...")
                except Exception as e:
                    logger.error(f"Screen Reader failed: {e}")
                    feedback_message = "I'm sorry, I couldn't describe your screen right now."
            else:
                logger.warning("Screen reading requested but no perception bundle or screen reader agent available")
                feedback_message = "I can't see your screen right now. Please ensure the app has proper permissions."

            # Convert to speech and return
            if feedback_message:
                audio_data = responder_agent.speak_feedback(feedback_message)
                audio_base64 = None
                if audio_data and len(audio_data) >= 44:
                    audio_base64 = base64.b64encode(audio_data).decode("ascii")
                    logger.info(f"Screen description converted to speech ({len(audio_data)} bytes)")

                return {
                    "feedback_message": feedback_message,
                    "spoken_response": feedback_message,
                    "spoken_audio": audio_base64,
                    "spoken_audio_format": "audio/wav" if audio_base64 else None,
                    "status": "completed",
                    "end_time": time.time(),
                }

        # === NORMAL FEEDBACK GENERATION ===
        # Track that the Responder agent is being used
        track_agent_usage(state, "responder")

        # Only use pre-set feedback message if execution failed
        # If execution succeeded, generate fresh success feedback
        if feedback_message and status in ["failed", "error", "retry"]:
            logger.info(
                f"Using feedback message from error handler: {feedback_message}"
            )
            return {
                "feedback_message": feedback_message,
                "end_time": time.time(),
                "status": status,
            }

        # If execution succeeded AND there's already a feedback_message set 
        # (e.g., from universal_agent_node), USE IT - don't regenerate
        if status in ["completed", "success", "executed"] and feedback_message:
            logger.info(f"Using existing feedback message: {feedback_message[:80]}...")
            # Convert to speech
            audio_data = responder_agent.speak_feedback(feedback_message)
            audio_base64 = None
            if audio_data and len(audio_data) >= 44:
                audio_base64 = base64.b64encode(audio_data).decode("ascii")
            
            return {
                "feedback_message": feedback_message,
                "spoken_response": feedback_message,
                "spoken_audio": audio_base64,
                "spoken_audio_format": "audio/wav" if audio_base64 else None,
                "end_time": time.time(),
                "status": "completed",
            }

        # Handle missing intent gracefully
        intent_obj = None
        if intent_dict:
            try:
                intent_obj = INTENT_OBJECT_MODEL(**intent_dict)
            except Exception as intent_error:
                logger.warning(
                    f"Failed to convert intent dict to object: {intent_error}"
                )
                intent_obj = None

        # Convert executed steps back to objects
        execution_results = None
        if executed_steps_data:
            try:
                from utils.types import ActionResult

                # Handle both dict and string formats
                processed_steps = []
                for step in executed_steps_data:
                    if isinstance(step, dict):
                        # Convert step dict to ActionResult format
                        # The real device executor returns: {"step": 1, "action": "open_app", "success": True, ...}
                        # ActionResult expects: {"action_type": "...", "success": ..., ...}
                        processed_steps.append(
                            ActionResult(
                                success=step.get("success", True),
                                action_type=step.get("action", "unknown"),
                                error_message=step.get("error"),
                                execution_time=step.get("execution_time", 0.0),
                                metadata={
                                    "step": step.get("step"),
                                    "description": step.get("description", ""),
                                    "coordinates": step.get("coordinates", {}),
                                    "timestamp": step.get("timestamp", time.time()),
                                },
                            )
                        )
                    elif isinstance(step, str):
                        # Convert string to ActionResult format
                        processed_steps.append(
                            ActionResult(
                                success=True,
                                action_type="unknown",
                                metadata={"details": step},
                                execution_time=0.0,
                            )
                        )
                execution_results = processed_steps
            except Exception as step_error:
                logger.warning(f"Failed to convert executed steps: {step_error}")
                execution_results = None

        # === GET FULL CONTEXT FOR CONVERSATIONAL AI ===
        full_context = None
        session = None
        
        # Extract transcript and goal for context-aware responses
        transcript = state.get("transcript") or state.get("command") or state.get("text_input")
        goal_summary = state.get("goal_summary")
        
        # Build completed steps summary for multi-step feedback
        completed_steps = []
        if executed_steps_data:
            for step in executed_steps_data:
                if isinstance(step, dict):
                    desc = step.get("description") or step.get("action", "action")
                    if step.get("success", True):
                        completed_steps.append(desc)
        
        try:
            from services.conversation_session import get_session_manager

            session = get_session_manager().get_session(session_id)
            full_context = session.get_full_context()
            logger.debug(f"Full context loaded: app={full_context.current_app}, responses={len(full_context.response_history)}")
        except Exception as ctx_error:
            logger.warning(f"Could not load full context: {ctx_error}")

        # Generate feedback message with FULL CONTEXT for conversational AI
        feedback_message = responder_agent.generate_feedback(
            intent_obj,
            status,
            execution_results,
            error_message,
            transcript=transcript,
            has_introduced=has_introduced,
            conversation_turn=conversation_turn,
            is_follow_up=is_follow_up,
            full_context=full_context,  # NEW: Pass full context for variation
            goal_summary=goal_summary,  # NEW: Pass goal for multi-step awareness
            completed_steps=completed_steps,  # NEW: Pass what was accomplished
        )

        # === UPDATE SESSION WITH NEW ENTITIES AND RESPONSE ===
        if session and intent_dict:
            try:
                # Track entities for pronoun resolution
                action = intent_dict.get("action", "")
                recipient = intent_dict.get("recipient")

                # Track app entities
                if action in ["open_app", "launch", "start"] and recipient:
                    session.push_entity("app", recipient)
                    session.current_app = recipient

                # Track contact entities
                if action in ["send_message", "make_call"] and recipient:
                    session.push_entity("contact", recipient)

                # Track last action
                session.last_action = action
                if recipient:
                    session.last_target = recipient

                # Track response for variation
                session.add_response(feedback_message)

                logger.debug(f"Session updated: app={session.current_app}, action={session.last_action}")

            except Exception as update_error:
                logger.warning(f"Session update failed: {update_error}")

        # Update session context if this was a greeting/introduction
        if (
            intent_dict
            and intent_dict.get("action") in ["greeting", "help"]
            and not has_introduced
        ):
            logger.info(
                f"Marking session {session_id} as introduced (turn {conversation_turn})"
            )
            # Update state to mark introduction
            state["has_introduced"] = True
            if session:
                session.mark_introduced()

        # Convert to speech and capture audio payload for clients
        audio_data = responder_agent.speak_feedback(feedback_message)
        audio_base64 = None
        if audio_data:
            # Validate audio before encoding - ensure it's not empty or corrupted
            if len(audio_data) < 44:  # WAV header minimum is 44 bytes
                logger.warning(
                    f"Audio data too small ({len(audio_data)} bytes), skipping"
                )
            else:
                audio_base64 = base64.b64encode(audio_data).decode("ascii")
                # Validate base64 encoding
                if not audio_base64 or len(audio_base64) < 50:
                    logger.warning(
                        f"Base64 audio encoding failed or too small ({len(audio_base64) if audio_base64 else 0} chars), skipping"
                    )
                    audio_base64 = None
                else:
                    logger.info(
                        f"Feedback converted to speech successfully ({len(audio_data)} bytes)"
                    )
        else:
            logger.info("Using text-only feedback (TTS unavailable)")

        # Record end time
        execution_time = time.time() - start_time

        # Prepare detailed output for workflow tracking
        output_details = {
            "feedback_message": feedback_message,
            "feedback_length": len(feedback_message) if feedback_message else 0,
            "has_audio": audio_data is not None,
            "audio_format": "audio/wav" if audio_data else None,
            "intent_processed": intent_obj is not None,
            "execution_results_count": (
                len(execution_results) if execution_results else 0
            ),
            "status_processed": status,
        }

        update_workflow_step(
            state,
            node_name,
            "completed",
            f"Response generated successfully: '{feedback_message[:100]}{'...' if len(feedback_message) > 100 else ''}'",
            output=output_details,
            execution_time=execution_time,
        )

        logger.info(f"Feedback generated: {feedback_message}")
        return {
            "feedback_message": feedback_message,
            "spoken_response": feedback_message,
            "spoken_audio": audio_base64,
            "spoken_audio_format": "audio/wav" if audio_base64 else None,
            "end_time": time.time(),
            "status": "completed",
        }

    except Exception as e:
        execution_time = time.time() - start_time

        # Generate a safe fallback message
        fallback_message = "I'm sorry, something went wrong with your request."
        if state.get("transcript"):
            fallback_message += f" I heard you say: '{state.get('transcript')}'"

        {
            "error_type": type(e).__name__,
            "error_message": str(e),
            "execution_time": execution_time,
            "fallback_message": fallback_message,
            "available_data": {
                "has_intent": bool(state.get("intent")),
                "has_executed_steps": bool(state.get("executed_steps")),
                "status": state.get("status", "unknown"),
            },
        }

        update_workflow_step(
            state,
            node_name,
            "failed",
            f"Response generation failed: {str(e)}",
            execution_time=execution_time,
        )

        logger.error(f"Speak node failed: {e}")

        return {
            "feedback_message": fallback_message,
            "spoken_response": fallback_message,
            "spoken_audio": None,
            "spoken_audio_format": None,
            "end_time": time.time(),
            "status": "failed",
        }


def error_handler_node(state: TaskState) -> Dict[str, Any]:
    """
    Error Handler node: Handle errors and generate recovery feedback.

    Args:
        state: Current task state with error information.

    Returns:
        State update with error handling results.
    """
    start_time = time.time()
    node_name = "Error Handler"

    try:
        logger.info("Error Handler node: Processing error recovery")
        add_workflow_step(
            state,
            node_name,
            "running",
            "Processing error and generating recovery feedback",
        )

        # Extract error information
        error_message = state.get("error_message", "Unknown error occurred")
        intent_dict = state.get("intent")
        retry_count = state.get("retry_count", 0)
        max_retries = state.get("max_retries", 3)
        transcript = state.get("transcript", "")

        # Determine error type for appropriate response
        error_type = "UNKNOWN"
        if error_message and isinstance(error_message, str):
            error_msg_lower = error_message.lower()
            if "timeout" in error_msg_lower:
                error_type = "TIMEOUT"
            elif "not found" in error_msg_lower:
                error_type = "ELEMENT_NOT_FOUND"
            elif "permission" in error_msg_lower or "accessibility" in error_msg_lower:
                error_type = "PERMISSION_DENIED"
            elif "network" in error_msg_lower:
                error_type = "NETWORK_ERROR"
            elif "ui data" in error_msg_lower or "screen data" in error_msg_lower:
                error_type = "NO_UI_DATA"
            elif "organization has been restricted" in error_msg_lower:
                error_type = "API_RESTRICTED"
            elif "stt" in error_msg_lower or "transcription" in error_msg_lower:
                error_type = "STT_FAILED"

        # Generate appropriate error message based on type
        if error_type == "API_RESTRICTED":
            recovery_message = "I'm sorry, there's an issue with my speech recognition service. Please try typing your message instead."
        elif error_type == "STT_FAILED":
            recovery_message = "I couldn't understand your voice message. Could you please try speaking more clearly or type your message?"
        elif error_type == "TIMEOUT":
            recovery_message = "The request took too long to process. Please try again."
        elif error_type == "NO_UI_DATA":
            recovery_message = "I can't see your screen right now. Please make sure the AURA Android app is open and has accessibility permissions enabled."
        elif error_type == "ELEMENT_NOT_FOUND":
            recovery_message = (
                "I couldn't find what you're looking for. Could you be more specific?"
            )
        elif error_type == "PERMISSION_DENIED":
            recovery_message = "I don't have permission to do that. Please check your accessibility settings."
        elif error_type == "NETWORK_ERROR":
            recovery_message = (
                "There seems to be a connection issue. Please try again in a moment."
            )
        elif transcript:
            recovery_message = f"I couldn't complete your request to '{transcript}'. Something went wrong on my end."
        else:
            recovery_message = "I'm sorry, something went wrong. Please try again."

        # Determine if we should retry
        should_retry = retry_count < max_retries and error_type in [
            "TIMEOUT",
            "NETWORK_ERROR",
        ]

        execution_time = time.time() - start_time

        # Prepare detailed output for workflow tracking
        output_details = {
            "error_type": error_type,
            "original_error": error_message,
            "recovery_message": recovery_message,
            "retry_count": retry_count,
            "should_retry": should_retry,
            "max_retries": max_retries,
            "has_transcript": bool(transcript),
            "has_intent": bool(intent_dict),
        }

        status = "retry" if should_retry else "failed"
        step_message = f"Error handled: {error_type}" + (
            ", preparing retry" if should_retry else ", no retry"
        )

        update_workflow_step(
            state,
            node_name,
            "completed" if not should_retry else "retry",
            step_message,
            output=output_details,
            execution_time=execution_time,
        )

        update_data = {
            "feedback_message": recovery_message,
            "retry_count": retry_count + 1 if should_retry else retry_count,
            "end_time": time.time(),
            "status": status,
        }

        logger.info(f"Error handled: {error_type}, retry: {should_retry}")
        return update_data

    except Exception as e:
        execution_time = time.time() - start_time
        error_details = {
            "error_type": type(e).__name__,
            "error_message": str(e),
            "execution_time": execution_time,
            "fallback_message": "I'm sorry, I encountered multiple issues and cannot continue.",
        }

        update_workflow_step(
            state,
            node_name,
            "failed",
            f"Error handler failed: {str(e)}",
            output=error_details,
            execution_time=execution_time,
        )

        logger.error(f"Error Handler node failed: {e}")
        return {
            "feedback_message": "I'm sorry, I encountered multiple issues and cannot continue.",
            "end_time": time.time(),
            "status": "failed",
        }


def validate_intent_node(state: TaskState) -> Dict[str, Any]:
    """
    Validate Intent node: Pre-validate intent before execution.

    Uses the Validator agent to check:
    - Intent structure completeness
    - Action type validity
    - Required fields presence
    - Dangerous action detection

    Args:
        state: Current task state with intent.

    Returns:
        State update with validation results.
    """
    start_time = time.time()
    node_name = "Validate Intent"

    try:
        logger.info("Validate Intent node: Pre-validating intent")
        add_workflow_step(
            state, node_name, "running", "Validating intent before execution"
        )

        # Track that the Validator agent is being used
        track_agent_usage(state, "validator")

        intent_dict = state.get("intent")
        if not intent_dict:
            logger.warning("No intent to validate, skipping")
            return {"status": "validation_skipped"}

        # Convert to IntentObject for validation
        intent_obj = INTENT_OBJECT_MODEL(**intent_dict)

        # Validate the intent using simple rules (0 LLM calls)
        # Validate intent using rule-based validation
        # Zero LLM calls - fast Python validation
        validation_result = validator_agent.validate_intent(intent_obj)

        execution_time = time.time() - start_time

        if not validation_result.is_valid:
            logger.warning(f"Intent validation failed: {validation_result.issues}")
            update_workflow_step(
                state,
                node_name,
                "completed_with_issues",
                f"Validation found {len(validation_result.issues)} issues",
                execution_time=execution_time,
            )

            return {
                "validation_result": validation_result.to_dict(),
                "status": (
                    "validation_warning"
                    if validation_result.confidence > 0.5
                    else "validation_failed"
                ),
            }

        update_workflow_step(
            state,
            node_name,
            "completed",
            "Intent validated successfully",
            execution_time=execution_time,
        )

        logger.info("Intent validation passed")
        return {
            "validation_result": validation_result.to_dict(),
            "status": "validated",
        }

    except Exception as e:
        execution_time = time.time() - start_time
        logger.error(f"Validate Intent node failed: {e}")
        update_workflow_step(
            state,
            node_name,
            "error",
            f"Validation error: {str(e)}",
            execution_time=execution_time,
        )
        # Don't block on validation errors, continue with warning
        return {
            "validation_result": {
                "is_valid": True,
                "confidence": 0.5,
                "issues": [str(e)],
            },
            "status": "validation_error",
        }


async def parallel_ui_and_validation_node(state: TaskState) -> Dict[str, Any]:
    """
    Parallel Processing node: Run UI analysis and validation concurrently.

    This node implements the fan-out/fan-in pattern:
    - Fan-out: Start UI analysis and validation in parallel
    - Fan-in: Merge results when both complete

    Benefits:
    - Reduced latency (both run simultaneously)
    - Early failure detection (validation can fail fast)
    - Better resource utilization

    Args:
        state: Current task state with intent.

    Returns:
        Combined state update from both parallel operations.
    """
    import asyncio

    start_time = time.time()
    node_name = "Parallel Processing"

    try:
        logger.info(
            "Parallel Processing node: Running UI analysis + validation concurrently"
        )
        add_workflow_step(
            state, node_name, "running", "Running parallel UI analysis and validation"
        )

        # Track parallel processing
        track_agent_usage(state, "parallel_processor")

        # Define async tasks for parallel execution
        async def run_ui_analysis():
            """Run UI analysis asynchronously."""
            # Note: Legacy automatic UI data capture removed - perception must be explicitly
            # requested via the Perception Controller via perception_node, not captured here.
            logger.warning("UI analysis skipped - Perception Controller must provide perception data")
            return {
                "success": False,
                "error": "UI perception data must come from Perception Controller",
            }

        async def run_validation():
            """Run intent validation asynchronously."""
            try:
                intent_dict = state.get("intent")
                if not intent_dict:
                    return {"success": True, "result": None}

                intent_obj = INTENT_OBJECT_MODEL(**intent_dict)
                validation_result = validator_agent.validate_intent(intent_obj)

                return {
                    "success": True,
                    "result": validation_result.to_dict(),
                    "is_valid": validation_result.is_valid,
                }
            except Exception as e:
                logger.error(f"Parallel validation failed: {e}")
                return {"success": False, "error": str(e)}

        # Run both tasks concurrently
        ui_task = asyncio.create_task(run_ui_analysis())
        validation_task = asyncio.create_task(run_validation())

        # Wait for both to complete
        ui_result, validation_result = await asyncio.gather(ui_task, validation_task)

        execution_time = time.time() - start_time
        logger.info(f"Parallel processing completed in {execution_time:.2f}s")

        # Process UI results
        # Note: Legacy UI data processing removed - perception data must come from
        # Perception Controller via perception_node, not processed here.
        ui_update = {}
        if not ui_result.get("success"):
            logger.warning(f"UI analysis failed in parallel: {ui_result.get('error')}")

        # Process validation results
        validation_update = {}
        if validation_result.get("success") and validation_result.get("result"):
            validation_update = {
                "validation_result": validation_result["result"],
            }
            track_agent_usage(state, "validator")

            if not validation_result.get("is_valid", True):
                logger.warning("Validation failed in parallel processing")

        # Combine results
        combined_update = {
            **ui_update,
            **validation_update,
            "status": "parallel_completed",
            "parallel_execution_time": execution_time,
        }

        update_workflow_step(
            state,
            node_name,
            "completed",
            f"Parallel processing completed: UI={ui_result.get('success')}, Validation={validation_result.get('success')}",
            execution_time=execution_time,
        )

        return combined_update

    except Exception as e:
        execution_time = time.time() - start_time
        logger.error(f"Parallel Processing node failed: {e}")
        update_workflow_step(
            state,
            node_name,
            "error",
            f"Parallel processing error: {str(e)}",
            execution_time=execution_time,
        )
        return {
            "error_message": f"Parallel processing failed: {str(e)}",
            "status": "failed",
        }


# Node initialization function (called from graph.py)
def initialize_nodes(
    app_settings: Settings,
    app_stt_service: STTService,
    app_llm_service: LLMService,
    app_vlm_service: VLMService,
    app_tts_service: TTSService,
    app_accessibility_service: RealAccessibilityService,
    app_device_executor_service: RealDeviceExecutorService,
    app_commander_agent: "CommanderAgent",
    app_responder_agent: "ResponderAgent",
    app_screen_vlm_agent: "ScreenVLM" = None,
    app_validator_agent: "ValidatorAgent" = None,
) -> None:
    """
    Initialize global service and agent instances for nodes.

    HYBRID ARCHITECTURE:
    - Commander: Groq (fast intent parsing)
    - UniversalAgent: Handles all UI actions
    - Responder: Groq (fast feedback)
    - ScreenVLM: VLM (visual understanding + location)
    - Validator: Groq (fast validation)

    Args:
        app_settings: Application settings.
        app_stt_service: Speech-to-text service.
        app_llm_service: Language model service.
        app_vlm_service: Vision-language model service.
        app_tts_service: Text-to-speech service.
        app_accessibility_service: Real accessibility service.
        app_device_executor_service: Real device executor service.
        app_commander_agent: Commander agent.
        app_responder_agent: Responder agent.
        app_screen_vlm_agent: ScreenVLM agent (optional).
        app_validator_agent: Validator agent (optional).
    """
    global settings, stt_service, llm_service, vlm_service, tts_service
    global accessibility_service, device_executor_service
    global commander_agent, responder_agent
    global screen_vlm_agent, validator_agent

    settings = app_settings
    stt_service = app_stt_service
    llm_service = app_llm_service
    vlm_service = app_vlm_service
    tts_service = app_tts_service
    accessibility_service = app_accessibility_service
    device_executor_service = app_device_executor_service
    commander_agent = app_commander_agent
    responder_agent = app_responder_agent
    screen_vlm_agent = app_screen_vlm_agent
    validator_agent = app_validator_agent

    logger.info(
        "LangGraph nodes initialized successfully with hybrid parallel architecture"
    )
    logger.info(
        "  - Agents: Commander, UniversalAgent, Responder"
        + (", ScreenVLM" if screen_vlm_agent else "")
        + (", Validator" if validator_agent else "")
    )
    logger.info(f"  - Parallel execution: {app_settings.enable_parallel_execution}")
