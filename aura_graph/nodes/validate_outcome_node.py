"""
Validate outcome node - Post-action validation for goal-driven execution.

This is the CRITICAL node that closes the observation-action-validation loop.
It checks if an action actually succeeded by comparing UI state before/after.

# RETRY SYSTEM: This is retry system 2 of 3 (LangGraph validate_outcome path).
# System 1: coordinator._handle_target_not_found() — DISABLED by FIX-007
# System 2: THIS FILE — validate_outcome → retry_router
# System 3: error_handler_node — catches exceptions from all systems
# See docs/AURA_RETRY_ARCHITECTURE.md for full picture.
"""

import logging
from typing import Any

from aura_graph.state import TaskState
from aura_graph.agent_state import (
    AgentState, AbortCondition, RetryStrategy, SuccessCriteria
)
from config.success_criteria import get_success_criteria
from services.ui_signature import compute_ui_signature, signatures_differ


logger = logging.getLogger(__name__)


def validate_outcome_node(state: TaskState) -> dict[str, Any]:
    """
    Validate that the last executed action achieved its intended effect.
    
    This node:
    1. Captures current UI state (post-action)
    2. Compares with pre-action UI signature
    3. Checks action-specific success criteria
    4. Updates AgentState with validation result
    5. Sets routing hints for next node (success/retry/abort)
    
    Returns:
        Dict with validation_result, agent_state updates, and routing hints
    """
    agent_state: AgentState = state.get("agent_state") or AgentState()
    perception_bundle = state.get("perception_bundle")
    executed_steps = state.get("executed_steps", [])
    
    # Get last executed action for criteria lookup
    last_action = _get_last_action(executed_steps)
    action_type = last_action.get("action_type", "unknown") if last_action else "unknown"
    
    # Get current UI signature
    ui_tree = None
    if perception_bundle and hasattr(perception_bundle, "ui_tree"):
        ui_tree = perception_bundle.ui_tree.elements if perception_bundle.ui_tree else None
    
    current_signature = compute_ui_signature(ui_tree)
    pre_action_signature = agent_state.last_ui_signature

    # FIXED: FIX-003 — populate package/activity from UI tree for target_screen_reached validation
    if ui_tree:
        root = ui_tree[0] if isinstance(ui_tree, list) and ui_tree else {}
        if isinstance(root, dict):
            pkg = root.get("packageName", "") or ""
            if pkg:
                agent_state.current_package_name = pkg
            # Some trees expose activityName on the root element
            act = root.get("activityName", "") or root.get("className", "") or ""
            if act:
                agent_state.current_activity_name = act

    # Get success criteria for this action type
    criteria = get_success_criteria(action_type)

    # Validate based on criteria
    validation_result = _validate_against_criteria(
        criteria=criteria,
        pre_signature=pre_action_signature,
        post_signature=current_signature,
        ui_tree=ui_tree,
        last_action=last_action,
        agent_state=agent_state,
    )
    
    # Update agent state
    agent_state.record_ui_signature(current_signature)
    agent_state.total_attempts += 1
    
    # Check abort conditions
    abort_condition = agent_state.check_abort_conditions()
    
    # Determine routing
    if abort_condition:
        routing = "abort"
        validation_result["abort_reason"] = abort_condition.value
        logger.warning(f"Abort condition met: {abort_condition.value}")
        _broadcast_task_abort(state.get("session_id", "default"), abort_condition.value)
    elif validation_result["success"]:
        routing = "success"
        # Mark subgoal complete if we have one
        if agent_state.goal and agent_state.goal.current_subgoal:
            agent_state.goal.current_subgoal.completed = True
        logger.info(f"Action {action_type} validated successfully")
        _broadcast_step_complete(state.get("session_id", "default"), success=True)
    else:
        routing = "retry"
        # Escalate retry strategy
        if agent_state.goal and agent_state.goal.current_subgoal:
            subgoal = agent_state.goal.current_subgoal
            subgoal.attempts += 1
            new_strategy = subgoal.escalate_strategy()
            validation_result["retry_strategy"] = new_strategy.value
            logger.info(f"Action {action_type} failed validation, escalating to {new_strategy.value}")
    
    return {
        "validation_result": validation_result,
        "validation_routing": routing,
        "agent_state": agent_state,
    }


def _broadcast_step_complete(session_id: str, success: bool) -> None:
    """Broadcast step completion to Android app."""
    try:
        from services.task_progress import get_task_progress_service
        service = get_task_progress_service()
        service.complete_current_step(session_id, success)
    except Exception as e:
        logger.debug(f"Failed to broadcast step complete: {e}")


def _broadcast_task_abort(session_id: str, reason: str) -> None:
    """Broadcast task abort to Android app."""
    try:
        from services.task_progress import get_task_progress_service
        service = get_task_progress_service()
        service.abort_task(session_id, reason)
    except Exception as e:
        logger.debug(f"Failed to broadcast task abort: {e}")


def _get_last_action(executed_steps: list) -> dict | None:
    """Extract the last executed action from steps list."""
    if not executed_steps:
        return None
    
    last_step = executed_steps[-1]
    if isinstance(last_step, dict):
        return last_step
    # Handle string format from older execution
    return {"action_type": "unknown"}


def _validate_against_criteria(
    criteria: SuccessCriteria,
    pre_signature: str | None,
    post_signature: str,
    ui_tree: dict | None,
    last_action: dict | None,
    agent_state: Any = None,
) -> dict[str, Any]:
    """
    Check if action outcome matches success criteria.
    
    Returns dict with:
    - success: bool
    - reason: str explaining the validation result
    - details: dict with specific checks performed
    """
    result = {
        "success": True,
        "reason": "All criteria passed",
        "details": {},
    }
    
    # Check UI change expectation
    if criteria.ui_changed:
        ui_changed = signatures_differ(pre_signature, post_signature)
        result["details"]["ui_changed"] = ui_changed
        
        if not ui_changed:
            result["success"] = False
            result["reason"] = "Expected UI to change but it remained the same"
            return result
    else:
        # Action shouldn't change UI (system actions)
        result["details"]["ui_unchanged_expected"] = True
    
    # Check for target element gone (for navigation actions)
    if criteria.target_element_gone and last_action:
        target = last_action.get("target") or last_action.get("element_description")
        if target and ui_tree:
            element_found = _find_element_in_tree(ui_tree, target)
            result["details"]["target_element_check"] = not element_found
            
            if element_found:
                result["success"] = False
                result["reason"] = f"Expected element '{target}' to disappear but it's still present"
                return result
    
    # Check for expected text appearance
    if criteria.text_appeared and ui_tree:
        text_found = _find_text_in_tree(ui_tree, criteria.text_appeared)
        result["details"]["text_appeared_check"] = text_found
        
        if not text_found:
            result["success"] = False
            result["reason"] = f"Expected text '{criteria.text_appeared}' did not appear"
            return result
    
    # Check for target screen — validates actual package/activity name
    # FIXED: FIX-003 — was always "not_implemented", now validates actual package/activity
    if criteria.target_screen_reached:
        target = criteria.target_screen_reached.lower().strip()
        current_package = getattr(agent_state, 'current_package_name', '') or ""
        current_activity = getattr(agent_state, 'current_activity_name', '') or ""

        package_match = bool(target and target in current_package.lower())
        activity_match = bool(target and target in current_activity.lower())
        screen_reached = package_match or activity_match

        result["details"]["target_screen_check"] = {
            "target": target,
            "current_package": current_package,
            "current_activity": current_activity,
            "matched": screen_reached,
        }

        if not screen_reached:
            result["success"] = False
            result["reason"] = (
                f"Target screen '{target}' not reached. "
                f"Current: {current_package}/{current_activity}"
            )
            logger.warning(
                f"target_screen_reached validation failed: target={target}, "
                f"current={current_package}/{current_activity}"
            )

    return result


def _find_element_in_tree(elements: list, target: str) -> bool:
    """Search for element matching target description in UI elements list."""
    if not elements:
        return False
    
    target_lower = target.lower()
    
    for elem in elements:
        if not isinstance(elem, dict):
            continue
        # Check text and content description
        text = (elem.get("text") or "").lower()
        desc = (elem.get("contentDescription") or "").lower()
        resource_id = (elem.get("resourceId") or "").lower()
        
        if target_lower in text or target_lower in desc or target_lower in resource_id:
            return True
    
    return False


def _find_text_in_tree(elements: list, text: str) -> bool:
    """Search for specific text in UI elements list."""
    if not elements:
        return False
    
    text_lower = text.lower()
    
    for elem in elements:
        if not isinstance(elem, dict):
            continue
        elem_text = (elem.get("text") or "").lower()
        
        if text_lower in elem_text:
            return True
    
    return False
