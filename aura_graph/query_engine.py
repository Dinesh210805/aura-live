"""
AuraQueryEngine — single entry point for all task execution requests.

Mirrors the reference coding agent's QueryEngine / submitMessage() pattern:

  - One engine per process (wraps the compiled LangGraph app)
  - submit_message() is the ONLY way to invoke the graph from outside
  - Yields TaskUpdate events as an AsyncIterator for real-time streaming
  - Creates one AuraContext per task; cleans up on completion / error
  - Integrates ProgressTracker as the event bus between graph and caller

Design goals:
  1. Decouple callers (WebSocket handlers, ADK tools, CLI) from graph internals
  2. Enable real-time streaming without changing node implementations
  3. Provide a single place for token tracking, retry classification, timeouts
  4. Feature-flagged: disabled → falls back to direct app.ainvoke() (safe)

Usage::

    engine = AuraQueryEngine(app=compiled_graph)
    async for update in engine.submit_message("open Spotify"):
        await websocket.send_json(update.to_dict())
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional, TYPE_CHECKING

from aura.registry.agent_registry import AgentRegistry, get_agent_registry
from aura.registry.tool_registry import ToolRegistry, get_tool_registry
from aura.streaming.progress_tracker import ProgressTracker
from aura.streaming.task_update import TaskUpdate, UpdateType
from utils.logger import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

# Environment flag — set AURA_QUERY_ENGINE_ENABLED=true to activate
_ENGINE_ENABLED_ENV = "AURA_QUERY_ENGINE_ENABLED"


def _engine_enabled() -> bool:
    """Check feature flag from settings (fail-open: disabled by default)."""
    try:
        from config.settings import get_settings
        return getattr(get_settings(), "query_engine_enabled", False)
    except Exception:
        return False


class AuraQueryEngine:
    """
    Session-scoped entry point for all AURA task execution.

    Wraps the compiled LangGraph app and exposes a streaming interface.
    One engine instance is shared across all WebSocket sessions in the process.

    Lifecycle::

        engine = AuraQueryEngine(app=compiled_graph)

        # Per request:
        async for update in engine.submit_message("open spotify", session_id="abc"):
            await ws.send_json(update.to_dict())

    The engine is stateless between requests — all per-task state lives in
    the AuraContext created for each submit_message() call.
    """

    def __init__(
        self,
        app: Any,
        agent_registry: Optional[AgentRegistry] = None,
        tool_registry: Optional[ToolRegistry] = None,
        task_timeout_seconds: float = 120.0,
    ) -> None:
        """
        Args:
            app: Compiled LangGraph application (from compile_aura_graph()).
            agent_registry: Optional override; defaults to process-global singleton.
            tool_registry: Optional override; defaults to process-global singleton.
            task_timeout_seconds: Hard timeout per task (default: 120 s).
        """
        self._app = app
        self._agents = agent_registry or get_agent_registry()
        self._tools = tool_registry or get_tool_registry()
        self._task_timeout = task_timeout_seconds

        # Active task registry: task_id → asyncio.Task (for cancellation)
        self._active_tasks: Dict[str, asyncio.Task] = {}

        logger.info(
            f"[AuraQueryEngine] Initialized "
            f"(timeout={task_timeout_seconds}s, "
            f"agents={len(self._agents)}, tools={len(self._tools)})"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def submit_message(
        self,
        user_input: str,
        session_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        track_workflow: bool = True,
    ) -> AsyncIterator[TaskUpdate]:
        """
        Execute a task from user input, yielding TaskUpdate events as they happen.

        This is the ONLY public entry point for task execution when the engine
        is enabled. Callers iterate over the returned async generator to consume
        real-time progress events.

        Args:
            user_input: Transcribed user command (text).
            session_id: Conversation session ID (generated if not provided).
            thread_id: LangGraph thread ID for state persistence across turns.
            config: Optional execution config overrides.
            track_workflow: Whether to record workflow steps in task state.

        Yields:
            TaskUpdate events in chronological order:
              TASK_STARTED → ... progress ... → TASK_COMPLETED / TASK_FAILED

        Example::

            async for update in engine.submit_message("play liked songs"):
                await ws.send_json(update.to_dict())
                if update.type in (UpdateType.TASK_COMPLETED, UpdateType.TASK_FAILED):
                    break
        """
        session_id = session_id or str(uuid.uuid4())[:8]
        task_id = f"streaming_{int(time.time() * 1000)}"

        # Create the tracker and collect events into a queue for yielding
        tracker = ProgressTracker(session_id=session_id, task_id=task_id)
        event_queue: asyncio.Queue[Optional[TaskUpdate]] = asyncio.Queue()

        async def _enqueue(update: TaskUpdate) -> None:
            await event_queue.put(update)

        tracker.add_callback(_enqueue)

        # Run the graph execution as a background task
        graph_task = asyncio.create_task(
            self._run_graph(
                user_input=user_input,
                session_id=session_id,
                task_id=task_id,
                thread_id=thread_id,
                tracker=tracker,
                config=config or {},
                track_workflow=track_workflow,
            ),
            name=f"aura-task-{task_id}",
        )
        self._active_tasks[task_id] = graph_task

        # Sentinel callback: signal queue completion when graph task ends
        def _on_graph_done(fut: asyncio.Future) -> None:
            event_queue.put_nowait(None)  # sentinel

        graph_task.add_done_callback(_on_graph_done)

        # Stream events until sentinel received
        try:
            while True:
                update = await event_queue.get()
                if update is None:
                    break
                yield update
        finally:
            self._active_tasks.pop(task_id, None)

    async def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a running task by task_id.

        Returns:
            True if the task was found and cancelled, False if not found.
        """
        task = self._active_tasks.get(task_id)
        if task and not task.done():
            task.cancel()
            logger.info(f"[AuraQueryEngine] Cancelled task {task_id}")
            return True
        return False

    # ------------------------------------------------------------------
    # Internal graph execution
    # ------------------------------------------------------------------

    async def _run_graph(
        self,
        user_input: str,
        session_id: str,
        task_id: str,
        thread_id: Optional[str],
        tracker: ProgressTracker,
        config: Dict[str, Any],
        track_workflow: bool,
    ) -> Dict[str, Any]:
        """
        Execute the LangGraph app with progress tracking.

        Creates the initial TaskState, invokes app.ainvoke(), and emits
        lifecycle events. All errors are caught and emitted as TASK_FAILED
        before re-raising (so the WebSocket layer can inform the client).

        Returns:
            Final TaskState dict from graph execution.
        """
        from services.command_logger import create_new_execution_logger, clear_execution_logger

        cmd_logger = None
        try:
            await tracker.task_started(f"Processing: {user_input[:80]}")

            # Build initial state
            initial_state = self._build_initial_state(
                user_input=user_input,
                session_id=session_id,
                task_id=task_id,
                config=config,
                track_workflow=track_workflow,
            )

            # Set up command logger (same as existing execute_aura_task_from_streaming)
            cmd_logger = create_new_execution_logger(
                task_id=task_id,
                user_command=user_input,
                session_id=session_id,
            )

            # Wire progress tracker into LangGraph config for nodes that support it
            langgraph_config = self._build_langgraph_config(
                thread_id=thread_id,
                session_id=session_id,
                task_id=task_id,
                tracker=tracker,
            )

            logger.info(
                f"[AuraQueryEngine] Invoking graph "
                f"(task={task_id}, session={session_id}, input={user_input[:60]!r})"
            )

            # Execute with timeout
            result = await asyncio.wait_for(
                self._app.ainvoke(initial_state, config=langgraph_config),
                timeout=self._task_timeout,
            )

            status = result.get("status", "completed")
            await tracker.task_completed(data={
                "status": status,
                "feedback_message": result.get("feedback_message", ""),
                # Forward fields needed by WebSocket callers to build task_result
                "spoken_response": result.get("spoken_response") or result.get("feedback_message", ""),
                "tts_response": result.get("tts_response"),
                "intent": result.get("intent"),
                "execution_time": result.get("execution_time", 0.0),
                "error_message": result.get("error_message"),
                "debug_info": result.get("debug_info", {}),
            })

            # Finalize + upload GCS log (non-fatal)
            await self._finalize(cmd_logger, status, task_id, result)

            return result

        except asyncio.TimeoutError:
            error_msg = f"Task timed out after {self._task_timeout}s"
            logger.error(f"[AuraQueryEngine] {error_msg} (task={task_id})")
            await tracker.task_failed(error_msg)
            if cmd_logger:
                await self._finalize(cmd_logger, "timeout", task_id, {})
            raise

        except asyncio.CancelledError:
            logger.info(f"[AuraQueryEngine] Task cancelled (task={task_id})")
            await tracker.emit(
                UpdateType.TASK_FAILED,
                data={"error": "cancelled"},
                message="Task cancelled",
            )
            if cmd_logger:
                await self._finalize(cmd_logger, "cancelled", task_id, {})
            raise

        except Exception as exc:
            logger.error(f"[AuraQueryEngine] Graph error (task={task_id}): {exc}", exc_info=True)
            await tracker.task_failed(str(exc))
            if cmd_logger:
                await self._finalize(cmd_logger, "failed", task_id, {})
            raise

    # ------------------------------------------------------------------
    # State / config builders
    # ------------------------------------------------------------------

    def _build_initial_state(
        self,
        user_input: str,
        session_id: str,
        task_id: str,
        config: Dict[str, Any],
        track_workflow: bool,
    ) -> Dict[str, Any]:
        """
        Build the initial TaskState dict for the graph invocation.

        Matches the structure expected by `_create_initial_state()` in graph.py
        but driven by text input (no audio bytes).
        """
        return {
            "session_id": session_id,
            "raw_audio": None,
            "transcript": user_input,
            "streaming_transcript": user_input,
            "input_type": "streaming",
            "intent": None,
            "ui_screenshot": None,
            "ui_elements": [],
            "plan": [],
            "executed_steps": [],
            "current_step": 0,
            "status": "starting",
            "feedback_message": "",
            "error_message": None,
            "retry_count": 0,
            "max_retries": config.get("max_retries", 3),
            "goal_summary": None,
            "agent_state": None,
            "start_time": time.time(),
            "end_time": None,
            "execution_time": 0.0,
            "execution_mode": config.get("execution_mode", "live"),
            "task_id": task_id,
            "workflow_steps": [] if track_workflow else None,
            "track_workflow": track_workflow,
        }

    def _build_langgraph_config(
        self,
        thread_id: Optional[str],
        session_id: str,
        task_id: str,
        tracker: ProgressTracker,
    ) -> Dict[str, Any]:
        """
        Build the config dict passed to app.ainvoke().

        The `configurable` sub-dict is LangGraph's convention for thread IDs
        and custom node configuration. We also pass `tracker` here so nodes
        that are updated to accept it can emit progress events directly.
        """
        cfg: Dict[str, Any] = {
            "configurable": {
                "thread_id": thread_id or session_id,
                "session_id": session_id,
                "task_id": task_id,
                "progress_tracker": tracker,
            },
            "recursion_limit": 100,
        }
        return cfg

    # ------------------------------------------------------------------
    # Log finalization (non-fatal)
    # ------------------------------------------------------------------

    @staticmethod
    async def _finalize(
        cmd_logger: Any,
        status: str,
        task_id: str,
        result: Dict[str, Any],
    ) -> None:
        """Finalize execution log and upload to GCS. Errors are non-fatal."""
        try:
            cmd_logger.finalize(status=status)
        except Exception as err:
            logger.error(f"[AuraQueryEngine] Log finalize error: {err}")

        try:
            from gcs_log_uploader import upload_log_to_gcs_async
            from services.command_logger import clear_execution_logger

            log_path = cmd_logger.get_log_file_path()
            log_url = await upload_log_to_gcs_async(log_path, task_id)
            if log_url:
                result["log_url"] = log_url
        except Exception as gcs_err:
            logger.warning(f"[AuraQueryEngine] GCS upload skipped: {gcs_err}")
        finally:
            try:
                from services.command_logger import clear_execution_logger
                clear_execution_logger()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def active_task_count(self) -> int:
        """Number of currently running tasks."""
        return len(self._active_tasks)

    @property
    def active_task_ids(self) -> List[str]:
        """Snapshot of currently running task IDs."""
        return list(self._active_tasks.keys())

    def __repr__(self) -> str:
        return (
            f"<AuraQueryEngine active={self.active_task_count} "
            f"timeout={self._task_timeout}s>"
        )
