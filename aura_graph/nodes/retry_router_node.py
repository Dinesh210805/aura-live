"""
Retry router node - Implements retry strategy escalation.

Routes failed actions through different retry strategies based on
the current escalation level in the retry ladder.
"""

import logging
from typing import Any

from aura_graph.state import TaskState
from aura_graph.agent_state import AgentState, RetryStrategy


logger = logging.getLogger(__name__)


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
    retry_action = _get_retry_action(strategy, state)
    
    return {
        "retry_action": retry_action,
        "retry_strategy": strategy.value,
    }


def _get_retry_action(strategy: RetryStrategy, state: TaskState) -> dict[str, Any]:
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
        return {
            "type": "scroll_then_retry",
            "scroll_direction": "down",  # Default, could be smarter
            "action": last_action,
            "reason": "Element may be off-screen, scrolling to find it",
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
