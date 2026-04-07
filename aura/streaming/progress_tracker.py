"""
ProgressTracker — emits TaskUpdate events to registered callbacks.

Agents and nodes call tracker.emit(...) to push progress events.
The AuraQueryEngine wires up the WebSocket send function as the callback.

This decouples progress emission from the transport layer — the same tracker
works for WebSocket streaming, logging, or test assertion callbacks.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Coroutine, Dict, List, Optional, Union

from .task_update import TaskUpdate, UpdateType
from utils.logger import get_logger

logger = get_logger(__name__)

# Callback types: sync or async functions that receive a TaskUpdate
SyncCallback = Callable[[TaskUpdate], None]
AsyncCallback = Callable[[TaskUpdate], Coroutine[Any, Any, None]]
ProgressCallback = Union[SyncCallback, AsyncCallback]


class ProgressTracker:
    """
    Centralized progress event bus for a single task execution.

    One ProgressTracker is created per task (inside AuraContext) and
    discarded when the task completes. Callbacks are registered once
    and receive all events emitted during the task lifetime.

    Usage (in nodes/agents)::

        context.progress.emit(
            UpdateType.EXECUTING_GESTURE,
            data={"action": "tap", "target": "Play button"},
            message="Tapping Play button",
        )

    Usage (in query engine / websocket handler)::

        tracker = ProgressTracker(session_id, task_id)
        tracker.add_callback(websocket_send_fn)
        context = AuraContext(..., progress=tracker)
    """

    def __init__(self, session_id: str, task_id: str) -> None:
        self.session_id = session_id
        self.task_id = task_id
        self._callbacks: List[ProgressCallback] = []
        self._history: List[TaskUpdate] = []

    # ------------------------------------------------------------------
    # Callback management
    # ------------------------------------------------------------------

    def add_callback(self, callback: ProgressCallback) -> None:
        """Register a callback to receive all future progress events."""
        self._callbacks.append(callback)

    def remove_callback(self, callback: ProgressCallback) -> None:
        """Unregister a previously registered callback."""
        self._callbacks = [cb for cb in self._callbacks if cb is not callback]

    # ------------------------------------------------------------------
    # Emission
    # ------------------------------------------------------------------

    async def emit(
        self,
        update_type: UpdateType,
        data: Optional[Dict[str, Any]] = None,
        message: Optional[str] = None,
    ) -> None:
        """
        Create and dispatch a TaskUpdate to all registered callbacks.

        Non-fatal: callback errors are caught and logged so one broken
        callback (e.g. a disconnected WebSocket) doesn't abort the task.
        """
        update = TaskUpdate(
            type=update_type,
            session_id=self.session_id,
            task_id=self.task_id,
            data=data or {},
            message=message,
        )
        self._history.append(update)

        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(update)
                else:
                    callback(update)
            except Exception as exc:
                # Don't let a broken callback kill the task
                logger.warning(
                    f"[ProgressTracker] Callback error for {update_type.value}: {exc}"
                )

    # ------------------------------------------------------------------
    # Convenience shorthands used by nodes
    # ------------------------------------------------------------------

    async def task_started(self, message: Optional[str] = None) -> None:
        await self.emit(UpdateType.TASK_STARTED, message=message or "Task started")

    async def task_completed(self, data: Optional[Dict] = None) -> None:
        await self.emit(UpdateType.TASK_COMPLETED, data=data, message="Task completed")

    async def task_failed(self, error: str) -> None:
        await self.emit(UpdateType.TASK_FAILED, data={"error": error}, message=f"Task failed: {error}")

    async def perceiving(self) -> None:
        await self.emit(UpdateType.PERCEIVING_SCREEN, message="Perceiving screen...")

    async def screen_perceived(self, element_count: int) -> None:
        await self.emit(
            UpdateType.SCREEN_PERCEIVED,
            data={"element_count": element_count},
            message=f"Screen perceived ({element_count} elements)",
        )

    async def executing_gesture(self, action: str, target: Optional[str] = None) -> None:
        await self.emit(
            UpdateType.EXECUTING_GESTURE,
            data={"action": action, "target": target},
            message=f"Executing {action}" + (f" on {target}" if target else ""),
        )

    async def planning(self, goal: Optional[str] = None) -> None:
        await self.emit(
            UpdateType.PLANNING,
            data={"goal": goal},
            message="Planning steps" + (f" for: {goal}" if goal else ""),
        )

    async def status(self, message: str, data: Optional[Dict] = None) -> None:
        await self.emit(UpdateType.STATUS_UPDATE, data=data, message=message)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def history(self) -> List[TaskUpdate]:
        """All events emitted so far (copy)."""
        return list(self._history)
