"""
Next subgoal node - Manages progression through subgoal stack.

After a subgoal completes successfully, this node advances to the
next subgoal or marks the goal as complete.
"""

import logging
from typing import Any

from aura_graph.state import TaskState
from aura_graph.agent_state import AgentState


logger = logging.getLogger(__name__)


def next_subgoal_node(state: TaskState) -> dict[str, Any]:
    """
    Advance to the next subgoal after successful completion.
    
    This node:
    1. Checks if current subgoal is complete
    2. Advances to next subgoal if available
    3. Marks goal complete if all subgoals done
    4. Returns routing hint for graph edges
    
    Returns:
        Dict with agent_state and goal_status
    """
    agent_state: AgentState = state.get("agent_state") or AgentState()
    
    if not agent_state.goal:
        logger.warning("No goal in agent state, nothing to advance")
        return {
            "agent_state": agent_state,
            "goal_status": "no_goal",
        }
    
    goal = agent_state.goal
    
    # Check if goal is already complete or aborted
    if goal.completed:
        logger.info(f"Goal already complete: {goal.description}")
        return {
            "agent_state": agent_state,
            "goal_status": "completed",
        }
    
    if goal.aborted:
        logger.info(f"Goal was aborted: {goal.abort_reason}")
        return {
            "agent_state": agent_state,
            "goal_status": "aborted",
        }
    
    # Advance to next subgoal
    next_subgoal = goal.advance_subgoal()
    
    if next_subgoal is None:
        # All subgoals complete
        logger.info(f"All subgoals complete for goal: {goal.description}")
        return {
            "agent_state": agent_state,
            "goal_status": "completed",
        }
    
    logger.info(f"Advancing to subgoal {goal.current_subgoal_index + 1}/{len(goal.subgoals)}: "
                f"{next_subgoal.action_type} - {next_subgoal.description}")
    
    return {
        "agent_state": agent_state,
        "goal_status": "in_progress",
        "current_subgoal": {
            "index": goal.current_subgoal_index,
            "action_type": next_subgoal.action_type,
            "target": next_subgoal.target,
            "description": next_subgoal.description,
        },
    }


def get_current_subgoal_action(state: TaskState) -> dict[str, Any] | None:
    """
    Helper to extract current subgoal as an action dict for execution.
    
    Used by execute_node to know what action to perform.
    """
    agent_state: AgentState = state.get("agent_state")
    if not agent_state or not agent_state.goal:
        return None
    
    subgoal = agent_state.goal.current_subgoal
    if not subgoal:
        return None
    
    return {
        "action_type": subgoal.action_type,
        "target": subgoal.target,
        "description": subgoal.description,
        **subgoal.parameters,
    }
