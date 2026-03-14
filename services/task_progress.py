"""
Task progress service - Broadcasts decomposed task progress to connected clients.

Sends WebSocket messages to Android app showing todo-style task lists
that update as subgoals complete.
"""

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Optional
from weakref import WeakSet

from fastapi import WebSocket
from utils.logger import get_logger


logger = get_logger(__name__)


def _run_async_safe(coro):
    """
    Run an async coroutine safely from any context (sync thread or async).
    
    When called from a background thread (e.g. asyncio.to_thread), schedules
    the coroutine on the main event loop so WebSocket sends work correctly.
    """
    try:
        loop = asyncio.get_running_loop()
        # We're in an async context - schedule the task
        asyncio.create_task(coro)
    except RuntimeError:
        # No running event loop in current thread.
        # Try to schedule on the main loop if one exists.
        try:
            import asyncio as _aio
            # Get all running loops — use the one from the main thread
            main_loop = _aio.get_event_loop_policy().get_event_loop()
            if main_loop.is_running():
                main_loop.call_soon_threadsafe(
                    lambda c=coro: main_loop.create_task(c)
                )
                return
        except Exception:
            pass
        # Fallback: run in a new thread (won't share WebSocket connections)
        def run_in_thread():
            try:
                asyncio.run(coro)
            except Exception as e:
                logger.debug(f"Async broadcast failed in thread: {e}")
        
        thread = threading.Thread(target=run_in_thread, daemon=True)
        thread.start()


@dataclass
class TaskProgressItem:
    """A single task item for display."""
    id: int
    description: str
    status: str  # "pending", "in_progress", "completed", "failed"
    action_type: str


@dataclass
class TaskProgress:
    """Current task progress state for a session."""
    session_id: str
    goal_description: str
    items: list[TaskProgressItem] = field(default_factory=list)
    current_index: int = 0
    is_complete: bool = False
    is_aborted: bool = False


class TaskProgressService:
    """
    Manages task progress broadcasting to connected WebSocket clients.
    
    Sends messages like:
    {
        "type": "task_progress",
        "goal": "Send message to John on WhatsApp",
        "tasks": [
            {"id": 1, "description": "Open WhatsApp", "status": "completed"},
            {"id": 2, "description": "Find contact John", "status": "in_progress"},
            {"id": 3, "description": "Send message", "status": "pending"}
        ],
        "current_task": 2,
        "total_tasks": 3
    }
    """
    
    def __init__(self):
        self._websockets: WeakSet[WebSocket] = WeakSet()
        self._sessions: dict[str, TaskProgress] = {}
        self._cancel_events: dict[str, threading.Event] = {}
    
    def register_websocket(self, ws: WebSocket) -> None:
        """Register a WebSocket connection for progress updates."""
        self._websockets.add(ws)
        logger.debug(f"WebSocket registered, total: {len(self._websockets)}")
    
    def unregister_websocket(self, ws: WebSocket) -> None:
        """Unregister a WebSocket connection."""
        self._websockets.discard(ws)
        logger.debug(f"WebSocket unregistered, total: {len(self._websockets)}")
    
    def start_task(
        self, 
        session_id: str, 
        goal_description: str,
        subgoals: list[dict[str, Any]]
    ) -> TaskProgress:
        """
        Start tracking a new decomposed task.
        
        Args:
            session_id: Session identifier
            goal_description: Human-readable goal description
            subgoals: List of subgoal dicts with description, action_type
            
        Returns:
            TaskProgress object
        """
        items = [
            TaskProgressItem(
                id=i + 1,
                description=sg.get("description", f"Step {i + 1}"),
                status="pending",
                action_type=sg.get("action_type", "unknown")
            )
            for i, sg in enumerate(subgoals)
        ]
        
        if items:
            items[0].status = "in_progress"
        
        progress = TaskProgress(
            session_id=session_id,
            goal_description=goal_description,
            items=items,
            current_index=0
        )
        
        self._sessions[session_id] = progress
        self._cancel_events[session_id] = threading.Event()
        
        # Broadcast initial progress (handles both sync and async contexts)
        _run_async_safe(self._broadcast_progress(progress))
        
        logger.info(f"📋 Task started: {goal_description} ({len(items)} steps)")
        return progress
    
    def complete_current_step(self, session_id: str, success: bool = True) -> Optional[TaskProgress]:
        """
        Mark current step as complete and advance to next.
        
        Args:
            session_id: Session identifier
            success: Whether step completed successfully
            
        Returns:
            Updated TaskProgress or None if session not found
        """
        progress = self._sessions.get(session_id)
        if not progress:
            return None
        
        # Mark current as completed/failed
        if progress.current_index < len(progress.items):
            progress.items[progress.current_index].status = "completed" if success else "failed"
        
        # Advance to next
        progress.current_index += 1
        
        if progress.current_index < len(progress.items):
            progress.items[progress.current_index].status = "in_progress"
        else:
            progress.is_complete = True
        
        # Broadcast update (handles both sync and async contexts)
        _run_async_safe(self._broadcast_progress(progress))
        
        logger.info(f"✅ Step {progress.current_index}/{len(progress.items)} complete")
        return progress
    
    def abort_task(self, session_id: str, reason: str = "aborted") -> Optional[TaskProgress]:
        """Mark task as aborted and signal cancellation."""
        progress = self._sessions.get(session_id)
        if not progress:
            return None
        
        progress.is_aborted = True
        if progress.current_index < len(progress.items):
            progress.items[progress.current_index].status = "failed"
        
        # Signal the cancel event so coordinator loop stops
        cancel_evt = self._cancel_events.get(session_id)
        if cancel_evt:
            cancel_evt.set()
        
        # Broadcast update (handles both sync and async contexts)
        _run_async_safe(self._broadcast_progress(progress))
        
        logger.warning(f"❌ Task aborted: {reason}")
        return progress
    
    def is_cancelled(self, session_id: str) -> bool:
        """Check if a task has been cancelled (thread-safe)."""
        evt = self._cancel_events.get(session_id)
        return evt.is_set() if evt else False
    
    def clear_session(self, session_id: str) -> None:
        """Clear progress for a session."""
        self._sessions.pop(session_id, None)
        self._cancel_events.pop(session_id, None)
    
    async def _broadcast_progress(self, progress: TaskProgress) -> None:
        """Broadcast progress to all connected WebSockets."""
        message = {
            "type": "task_progress",
            "session_id": progress.session_id,
            "goal": progress.goal_description,
            "tasks": [
                {
                    "id": item.id,
                    "description": item.description,
                    "status": item.status,
                    "action_type": item.action_type
                }
                for item in progress.items
            ],
            "current_task": progress.current_index + 1,
            "total_tasks": len(progress.items),
            "is_complete": progress.is_complete,
            "is_aborted": progress.is_aborted
        }
        
        dead_sockets = []
        for ws in self._websockets:
            try:
                await ws.send_json(message)
            except Exception as e:
                logger.debug(f"Failed to send to WebSocket: {e}")
                dead_sockets.append(ws)
        
        # Clean up dead connections
        for ws in dead_sockets:
            self._websockets.discard(ws)
    
    def get_progress(self, session_id: str) -> Optional[TaskProgress]:
        """Get current progress for a session."""
        return self._sessions.get(session_id)
    
    def emit_agent_status(self, agent: str, output: str) -> None:
        """
        Emit an agent status update to all connected clients.
        
        Shows real-time agent pipeline activity in Android UI.
        
        Args:
            agent: Name of the agent (e.g., "ReasoningEngine", "Commander")
            output: Short status output (e.g., "Opening Spotify...")
        """
        _run_async_safe(self._broadcast_agent_status(agent, output))
        logger.info(f"🤖 Agent status: {agent}: {output[:50]}...")
    
    async def _broadcast_agent_status(self, agent: str, output: str) -> None:
        """Broadcast agent status to all connected WebSockets."""
        message = {
            "type": "agent_status",
            "agent": agent,
            "output": output,
        }
        
        dead_sockets = []
        for ws in self._websockets:
            try:
                await ws.send_json(message)
            except Exception as e:
                logger.debug(f"Failed to send agent status: {e}")
                dead_sockets.append(ws)
        
        # Clean up dead connections
        for ws in dead_sockets:
            self._websockets.discard(ws)


# Singleton instance
_task_progress_service: Optional[TaskProgressService] = None


def get_task_progress_service() -> TaskProgressService:
    """Get or create the singleton task progress service."""
    global _task_progress_service
    if _task_progress_service is None:
        _task_progress_service = TaskProgressService()
    return _task_progress_service
