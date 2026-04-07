"""
AuraContext — session-scoped state container for task execution.

Mirrors the reference coding agent's ToolUseContext + AppState pattern:
  - One AuraContext per task (not per agent)
  - Cloned for sub-agents so child state doesn't pollute parent
  - Carries shared services (registries, progress tracker, task state)
  - Exposes spawn_agent() for orchestrated sub-agent invocation

This is the single object that flows through the entire execution graph.
Agents receive it in invoke(); tools receive it in call().

Key design decisions:
  - task_state is a mutable dict (matches LangGraph's TaskState TypedDict)
  - progress tracker is session-scoped (one tracker per task, shared)
  - agent/tool registries are process-global singletons
  - cloning creates a shallow copy of task_state for sub-agents
"""

from __future__ import annotations

import copy
import time
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

from aura.registry.agent_registry import AgentRegistry, get_agent_registry
from aura.registry.tool_registry import ToolRegistry, get_tool_registry
from aura.streaming.progress_tracker import ProgressTracker
from aura.streaming.task_update import UpdateType
from utils.logger import get_logger

if TYPE_CHECKING:
    from aura.core.agent import Agent, AgentResult
    from aura.core.tool import Tool, ToolResult

logger = get_logger(__name__)


class AuraContext:
    """
    Session-scoped execution context for a single AURA task.

    Passed to every agent and tool during task execution. Provides:
      - Shared task state (mutable dict, same reference across agents)
      - Progress tracker for real-time WebSocket streaming
      - Agent and tool registries for dynamic lookup
      - spawn_agent() for safe sub-agent invocation
      - _attachment_triggers: prevents duplicate context injections (e.g. CLAUDE.md)

    Sub-agents get a CLONED context so mutations to task_state in a child
    agent don't automatically propagate to the parent. The parent merges
    selected fields from the child result explicitly (controlled updates).

    Usage in a node/agent::

        result = await context.spawn_agent("planner", {"goal": "open Spotify"})
        context.task_state["plan"] = result.output["plan"]
        await context.progress.planning(goal="open Spotify")
    """

    def __init__(
        self,
        session_id: str,
        task_id: str,
        task_state: Dict[str, Any],
        progress: ProgressTracker,
        agent_registry: Optional[AgentRegistry] = None,
        tool_registry: Optional[ToolRegistry] = None,
        parent_context: Optional["AuraContext"] = None,
        depth: int = 0,
    ) -> None:
        self.session_id = session_id
        self.task_id = task_id
        self.task_state: Dict[str, Any] = task_state
        self.progress = progress

        # Use provided registries or fall back to process-global singletons
        self.agents: AgentRegistry = agent_registry or get_agent_registry()
        self.tools: ToolRegistry = tool_registry or get_tool_registry()

        # Parent link (for debugging sub-agent chains)
        self._parent = parent_context
        self._depth = depth

        # Tracks which context attachments have been injected (e.g. CLAUDE.md equivalents)
        # Prevents duplicate injection across turns — mirrors reference's nestedMemoryAttachmentTriggers
        self._attachment_triggers: Set[str] = (
            set(parent_context._attachment_triggers) if parent_context else set()
        )

        # Per-context message log (sub-agent messages don't pollute parent)
        self._messages: List[Dict[str, Any]] = []

        # Timing
        self._created_at = time.time()

    # ------------------------------------------------------------------
    # Sub-agent spawning (core reference pattern)
    # ------------------------------------------------------------------

    async def spawn_agent(
        self,
        agent_name: str,
        input_data: Dict[str, Any],
        merge_state_keys: Optional[List[str]] = None,
    ) -> "AgentResult":
        """
        Invoke a registered agent as a sub-agent.

        Creates a CLONED context for the child agent so its state mutations
        don't affect the parent. After the child completes, selected keys
        from child task_state are merged back into parent task_state.

        Args:
            agent_name: Name as registered in AgentRegistry.
            input_data: Input dict matching the agent's input_schema.
            merge_state_keys: If provided, copy these keys from child
                              task_state back to parent after completion.

        Returns:
            AgentResult from the child agent.

        Raises:
            KeyError: If agent_name is not in the registry.
        """
        from aura.core.agent import AgentResult

        agent = self.agents.require(agent_name)

        # Clone context for the child — child can mutate freely
        child_context = self._clone_for_child()

        logger.debug(
            f"[AuraContext] Spawning sub-agent {agent_name!r} "
            f"(depth={self._depth + 1}, session={self.session_id})"
        )

        await self.progress.emit(
            UpdateType.AGENT_STARTED,
            data={"agent": agent_name, "depth": self._depth + 1},
            message=f"Starting {agent_name}...",
        )

        try:
            result = await agent.invoke(input_data, child_context)

            # Selective state merge back to parent
            if merge_state_keys and result.success:
                for key in merge_state_keys:
                    if key in child_context.task_state:
                        self.task_state[key] = child_context.task_state[key]
                        logger.debug(
                            f"[AuraContext] Merged state key {key!r} from {agent_name}"
                        )

            # Propagate any new messages from child to parent log
            self._messages.extend(result.messages)

            await self.progress.emit(
                UpdateType.AGENT_COMPLETED,
                data={"agent": agent_name, "success": result.success},
                message=f"{agent_name} completed",
            )

            return result

        except Exception as exc:
            logger.error(f"[AuraContext] Sub-agent {agent_name!r} raised: {exc}")
            await self.progress.emit(
                UpdateType.TOOL_FAILED,
                data={"agent": agent_name, "error": str(exc)},
                message=f"{agent_name} failed: {exc}",
            )
            return AgentResult(
                success=False,
                error=str(exc),
                metadata={"agent": agent_name, "depth": self._depth + 1},
            )

    # ------------------------------------------------------------------
    # Tool invocation
    # ------------------------------------------------------------------

    async def call_tool(
        self,
        tool_name: str,
        args: Dict[str, Any],
    ) -> "ToolResult":
        """
        Invoke a registered tool with permission checking.

        Permission check runs first; if it raises PermissionError the tool
        is not called and a failed ToolResult is returned (fail-closed).

        Args:
            tool_name: Name as registered in ToolRegistry.
            args: Dict matching the tool's input_schema.

        Returns:
            ToolResult from the tool.
        """
        from aura.core.tool import ToolResult, PermissionError as ToolPermissionError

        tool = self.tools.find(tool_name)
        if tool is None:
            return ToolResult(
                success=False,
                error=f"Tool {tool_name!r} not found in registry",
            )

        await self.progress.emit(
            UpdateType.TOOL_CALLED,
            data={"tool": tool_name, "args": args},
            message=f"Calling tool: {tool_name}",
        )

        try:
            await tool.check_permissions(args, self)
        except ToolPermissionError as exc:
            logger.warning(f"[AuraContext] Tool {tool_name!r} permission denied: {exc}")
            return ToolResult(success=False, error=f"Permission denied: {exc}")

        try:
            result = await tool.call(args, self)
            await self.progress.emit(
                UpdateType.TOOL_COMPLETED,
                data={"tool": tool_name, "success": result.success},
            )
            return result
        except Exception as exc:
            logger.error(f"[AuraContext] Tool {tool_name!r} raised: {exc}")
            await self.progress.emit(
                UpdateType.TOOL_FAILED,
                data={"tool": tool_name, "error": str(exc)},
            )
            return ToolResult(success=False, error=str(exc))

    # ------------------------------------------------------------------
    # Attachment tracking (prevents duplicate context injections)
    # ------------------------------------------------------------------

    def mark_attachment(self, key: str) -> bool:
        """
        Mark a context attachment as injected.

        Returns:
            True if this is the first time (should inject),
            False if already injected (should skip).
        """
        if key in self._attachment_triggers:
            return False
        self._attachment_triggers.add(key)
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _clone_for_child(self) -> "AuraContext":
        """
        Create a shallow-cloned context for a sub-agent.

        task_state is deep-copied so child mutations don't affect parent.
        Registries and progress tracker are shared (they're process-global
        or session-scoped and safe to share).
        """
        child_task_state = copy.deepcopy(self.task_state)
        return AuraContext(
            session_id=self.session_id,
            task_id=self.task_id,
            task_state=child_task_state,
            progress=self.progress,  # shared — same tracker, same callbacks
            agent_registry=self.agents,
            tool_registry=self.tools,
            parent_context=self,
            depth=self._depth + 1,
        )

    def update_state(self, updates: Dict[str, Any]) -> None:
        """
        Apply a dict of updates to task_state (immutable-style helper).

        Does NOT mutate in-place; creates a new merged dict and replaces
        self.task_state. This matches the reference system's pattern of
        always returning new state objects.
        """
        self.task_state = {**self.task_state, **updates}

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def messages(self) -> List[Dict[str, Any]]:
        """All messages logged by this context and its sub-agents."""
        return list(self._messages)

    @property
    def age_seconds(self) -> float:
        """How long (in seconds) since this context was created."""
        return time.time() - self._created_at

    def __repr__(self) -> str:
        return (
            f"<AuraContext session={self.session_id!r} "
            f"task={self.task_id!r} depth={self._depth}>"
        )
