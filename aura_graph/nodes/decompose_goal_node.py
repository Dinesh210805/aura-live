"""
Decompose goal node - Breaks down complex goals into subgoals.

Uses Navigator agent to analyze current UI and create a step-by-step
plan for achieving multi-step goals. Broadcasts progress to Android app.
"""

import logging
from typing import Any

from aura_graph.state import TaskState
from aura_graph.agent_state import AgentState, Goal, Subgoal, SuccessCriteria
from config.success_criteria import get_success_criteria


logger = logging.getLogger(__name__)


def decompose_goal_node(state: TaskState) -> dict[str, Any]:
    """
    Break down a complex goal into executable subgoals.
    
    This node:
    1. Checks if decomposition is needed (multi-step goal)
    2. Uses existing plan from Navigator if available
    3. Converts plan steps into Subgoal objects
    4. Initializes AgentState with goal hierarchy
    5. Broadcasts task progress to Android app
    
    Returns:
        Dict with agent_state containing goal hierarchy
    """
    agent_state: AgentState = state.get("agent_state") or AgentState()
    intent = state.get("intent", {})
    plan = state.get("plan", [])
    original_request = state.get("original_request") or state.get("transcript") or state.get("streaming_transcript") or ""
    session_id = state.get("session_id", "default")
    
    # Check if this is a simple command (no decomposition needed)
    parameters = intent.get("parameters", {})
    pending_steps = parameters.get("steps", [])
    requires_decomposition = len(pending_steps) > 0 or len(plan) > 1
    
    if not requires_decomposition and len(plan) <= 1:
        # Simple command - create minimal goal structure
        goal = _create_simple_goal(intent, plan, original_request)
        agent_state.reset_for_new_goal(goal)
        
        logger.info(f"Simple goal created: {goal.description}")
        return {
            "agent_state": agent_state, 
            "original_request": original_request,
            "goal_summary": goal.description,  # For context-aware responses
        }
    
    # Complex goal - convert plan to subgoals
    goal = _create_complex_goal(intent, plan, pending_steps, original_request)
    agent_state.reset_for_new_goal(goal)
    
    logger.info(f"Complex goal decomposed into {len(goal.subgoals)} subgoals")
    for i, sg in enumerate(goal.subgoals):
        logger.debug(f"  Subgoal {i+1}: {sg.action_type} - {sg.description}")
    
    # Broadcast task progress to Android app
    _broadcast_task_start(session_id, goal)
    
    return {
        "agent_state": agent_state, 
        "original_request": original_request,
        "goal_summary": goal.description,  # For context-aware responses
    }


def _create_simple_goal(intent: dict, plan: list, original_request: str) -> Goal:
    """Create a goal structure for simple single-action commands."""
    action_type = intent.get("action", "unknown")
    target = intent.get("recipient") or intent.get("target") or intent.get("app")
    parameters = _extract_parameters(intent)
    
    # Generate human-readable description
    description = _generate_step_description(action_type, target, original_request)
    
    subgoal = Subgoal(
        description=description,
        action_type=action_type,
        target=target,
        parameters=parameters,
        success_criteria=get_success_criteria(action_type),
    )
    
    return Goal(
        original_utterance=original_request,
        description=description,
        subgoals=[subgoal],
    )


def _create_complex_goal(intent: dict, plan: list, pending_steps: list, original_request: str) -> Goal:
    """Create a goal structure for multi-step commands."""
    subgoals = []
    
    # First, add the primary action from intent
    primary_action = intent.get("action", "unknown")
    primary_target = intent.get("recipient") or intent.get("target") or intent.get("app")
    
    if primary_action != "unknown":
        primary_desc = _generate_step_description(primary_action, primary_target, "")
        subgoals.append(Subgoal(
            description=primary_desc,
            action_type=primary_action,
            target=primary_target,
            parameters=_extract_parameters(intent),
            success_criteria=get_success_criteria(primary_action),
        ))
    
    # Add pending steps from intent.parameters.steps
    for step in pending_steps:
        if isinstance(step, dict):
            action_type = step.get("action", step.get("action_type", "unknown"))
            target = step.get("target") or step.get("element_description")
            description = step.get("description") or _generate_step_description(action_type, target, "")
            parameters = {k: v for k, v in step.items() 
                         if k not in ("action", "action_type", "target", "description")}
        else:
            action_type = "unknown"
            target = None
            description = str(step)
            parameters = {}
        
        criteria = get_success_criteria(action_type)
        # Set target_screen_reached for open_app subgoals
        if action_type == "open_app" and target and criteria.target_screen_reached is not None:
            criteria.target_screen_reached = target.lower()
        subgoals.append(Subgoal(
            description=description,
            action_type=action_type,
            target=target,
            parameters=parameters,
            success_criteria=criteria,
        ))
    
    # Also add any steps from the plan (if Navigator created more)
    for step in plan:
        if isinstance(step, dict):
            action_type = step.get("action_type", step.get("action", "unknown"))
            # Skip if we already have this step from pending_steps
            if any(sg.action_type == action_type and sg.target == step.get("target") 
                   for sg in subgoals):
                continue
            
            target = step.get("target") or step.get("element_description")
            description = step.get("description") or _generate_step_description(action_type, target, "")
            parameters = {k: v for k, v in step.items() 
                         if k not in ("action_type", "action", "target", "description", "step")}
            
            subgoals.append(Subgoal(
                description=description,
                action_type=action_type,
                target=target,
                parameters=parameters,
                success_criteria=get_success_criteria(action_type),
            ))
    
    return Goal(
        original_utterance=original_request,
        description=_generate_goal_description(intent, original_request),
        subgoals=subgoals,
    )


def _extract_parameters(intent: dict) -> dict:
    """Extract action parameters from intent, excluding metadata fields."""
    exclude_keys = {"action", "app", "target", "recipient", "contact", "requires_decomposition", 
                    "confidence", "raw_text", "steps", "content"}
    params = intent.get("parameters", {})
    return {k: v for k, v in params.items() if k not in exclude_keys and v is not None}


def _generate_goal_description(intent: dict, original_request: str) -> str:
    """Generate a concise goal description from intent."""
    action = intent.get("action", "")
    recipient = intent.get("recipient", "")
    
    if recipient:
        return f"{_action_to_verb(action)} {recipient}"
    return original_request or action


def _generate_step_description(action_type: str, target: str | None, fallback: str) -> str:
    """Generate human-readable step description."""
    verb = _action_to_verb(action_type)
    
    if target:
        return f"{verb} {target}"
    
    if fallback:
        return fallback
    
    return verb


def _action_to_verb(action: str) -> str:
    """Convert action type to human-readable verb phrase."""
    verbs = {
        "open_app": "Open",
        "tap": "Tap on",
        "click": "Click on",
        "scroll": "Scroll",
        "scroll_down": "Scroll down",
        "scroll_up": "Scroll up",
        "type_text": "Type",
        "send_message": "Send message to",
        "make_call": "Call",
        "go_back": "Go back",
        "go_home": "Go to home screen",
        "take_screenshot": "Take screenshot",
        "read_screen": "Read screen",
        "wait": "Wait",
    }
    return verbs.get(action, action.replace("_", " ").title())


def _broadcast_task_start(session_id: str, goal: Goal) -> None:
    """Broadcast task progress to Android app via WebSocket."""
    try:
        from services.task_progress import get_task_progress_service
        
        service = get_task_progress_service()
        
        subgoals_data = [
            {
                "description": sg.description,
                "action_type": sg.action_type,
            }
            for sg in goal.subgoals
        ]
        
        service.start_task(
            session_id=session_id,
            goal_description=goal.description,
            subgoals=subgoals_data
        )
        
        logger.info(f"📤 Broadcast task start: {len(goal.subgoals)} steps")
        
    except Exception as e:
        logger.warning(f"Failed to broadcast task progress: {e}")
