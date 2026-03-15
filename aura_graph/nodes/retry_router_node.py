"""
Retry router node - Implements retry strategy escalation.

Routes failed actions through different retry strategies based on
the current escalation level in the retry ladder.

# RETRY SYSTEM: This is the escalation router for retry system 2 of 3.
# Routes validated failures through the 5-stage retry ladder.
"""

import logging
from typing import Any

from aura_graph.state import TaskState
from aura_graph.agent_state import AgentState, RetryStrategy


logger = logging.getLogger(__name__)


def _determine_scroll_direction(agent_state: AgentState, subgoal_target: str) -> str:
    """
    Determine scroll direction for SCROLL_AND_RETRY.
    # FIXED: FIX-010 — was hardcoded 'down'; now switches to 'up' after 2 attempts
    After 2 down-scrolls without finding target, try up.
    """
    if hasattr(agent_state, 'scroll_target') and agent_state.scroll_target != subgoal_target:
        agent_state.scroll_attempts_for_current_target = 0
        agent_state.scroll_target = subgoal_target

    attempts = getattr(agent_state, 'scroll_attempts_for_current_target', 0)
    if attempts >= 2:
        return "up"
    if hasattr(agent_state, 'scroll_attempts_for_current_target'):
        agent_state.scroll_attempts_for_current_target += 1
    return "down"


def retry_router_node(state: TaskState) -> dict[str, Any]:
    """
    Determine how to retry a failed action based on current strategy.
    
    Strategies in escalation order:
    1. SAME_ACTION - Retry exact same action (transient failure)
    2. ALTERNATE_SELECTOR - Try different element selector
    3. SCROLL_AND_RETRY - Scroll to find element, then retry
    4. VISION_FALLBACK - Use VLM for coordinate detection
    5. ABORT - Give up on this subgoal
    
    Returns:
        Dict with retry_action indicating how to proceed
    """
    agent_state: AgentState = state.get("agent_state") or AgentState()
    validation_result = state.get("validation_result", {})
    
    # Get current retry strategy from validation result or agent state
    strategy_name = validation_result.get("retry_strategy")
    if strategy_name:
        strategy = RetryStrategy(strategy_name)
    elif agent_state.goal and agent_state.goal.current_subgoal:
        strategy = agent_state.goal.current_subgoal.current_strategy
    else:
        strategy = RetryStrategy.SAME_ACTION
    
    logger.info(f"Retry router processing with strategy: {strategy.value}")

    # Determine retry action based on strategy
    retry_action = _get_retry_action(strategy, state, agent_state=agent_state)

    # FIXED: FIX-014 — generate reflexion lesson on abort for next attempt
    if retry_action.get("type") == "abort":
        try:
            from services.reflexion_service import get_reflexion_service
            reflexion = get_reflexion_service()
            if reflexion:
                import asyncio
                goal_str = ""
                if agent_state and agent_state.goal:
                    goal_str = getattr(agent_state.goal, 'original_utterance', '') or ""
                abort_reason = state.get("validation_result", {}).get("abort_reason", "unknown")
                # Fire and forget — don't block abort on lesson generation
                asyncio.create_task(
                    reflexion.generate_lesson(
                        goal=goal_str,
                        step_history=state.get("step_history", []),
                        failure_reason=abort_reason or "unknown"
                    )
                )
        except Exception as _e:
            logger.debug(f"Reflexion lesson generation skipped: {_e}")

    return {
        "retry_action": retry_action,
        "retry_strategy": strategy.value,
    }


def _get_retry_action(strategy: RetryStrategy, state: TaskState, agent_state: AgentState = None) -> dict[str, Any]:
    """
    Generate the appropriate retry action based on strategy.

    Returns a dict describing what to do next.
    """
    executed_steps = state.get("executed_steps", [])
    last_action = executed_steps[-1] if executed_steps else {}

    if isinstance(last_action, str):
        # Handle legacy string format
        last_action = {"action_type": "unknown", "description": last_action}
    
    if strategy == RetryStrategy.SAME_ACTION:
        return {
            "type": "repeat",
            "action": last_action,
            "modifications": None,
            "reason": "Retrying same action (transient failure assumed)",
        }
    
    elif strategy == RetryStrategy.ALTERNATE_SELECTOR:
        return {
            "type": "alternate_selector",
            "action": last_action,
            "modifications": {
                "use_content_description": True,
                "use_text_match": True,
                "relax_bounds": True,
            },
            "reason": "Trying alternate element selectors",
        }
    
    elif strategy == RetryStrategy.SCROLL_AND_RETRY:
        subgoal_target = last_action.get("target", "") if isinstance(last_action, dict) else ""
        scroll_dir = _determine_scroll_direction(agent_state, subgoal_target) if agent_state else "down"
        return {
            "type": "scroll_then_retry",
            "scroll_direction": scroll_dir,
            "action": last_action,
            "reason": f"Element may be off-screen, scrolling {scroll_dir} to find it",
        }
    
    elif strategy == RetryStrategy.VISION_FALLBACK:
        return {
            "type": "vision_fallback",
            "action": last_action,
            "modifications": {
                "force_screenshot": True,
                "use_vlm_coordinates": True,
            },
            "reason": "Using VLM vision to locate element by visual appearance",
        }
    
    elif strategy == RetryStrategy.ABORT:
        return {
            "type": "abort",
            "action": None,
            "reason": "All retry strategies exhausted",
        }
    
    # Default fallback
    return {
        "type": "repeat",
        "action": last_action,
        "reason": "Unknown strategy, defaulting to repeat",
    }


def should_use_perception_refresh(strategy: RetryStrategy) -> bool:
    """
    Determine if perception should be refreshed for this retry strategy.
    
    Some strategies need fresh UI state, others can reuse existing.
    """
    refresh_strategies = {
        RetryStrategy.SCROLL_AND_RETRY,
        RetryStrategy.VISION_FALLBACK,
        RetryStrategy.ALTERNATE_SELECTOR,
    }
    return strategy in refresh_strategies
