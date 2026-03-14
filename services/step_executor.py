"""
Step Executor Service for AURA backend.

Orchestrates the snapshot-analyze-act-verify loop for step-by-step automation
over WebSocket connections.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class StepResult:
    """Result of executing a single step."""

    step_id: str
    success: bool
    error: Optional[str] = None
    ui_after: Optional[Dict[str, Any]] = None
    duration_ms: float = 0


@dataclass
class ExecutionContext:
    """Context for a step-by-step execution session."""

    session_id: str
    websocket: Any  # WebSocket connection
    pending_ui_snapshot: Optional[asyncio.Future] = None
    pending_step_result: Optional[asyncio.Future] = None
    current_ui: Optional[Dict[str, Any]] = None
    steps_executed: List[StepResult] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)


class StepExecutor:
    """
    Executes action plans step-by-step with verification.

    Implements the Playwright-style loop:
    1. Request UI snapshot
    2. Analyze current state
    3. Execute action
    4. Verify result
    5. Continue or retry
    """

    def __init__(self, max_retries: int = 3, step_timeout: float = 10.0):
        self.max_retries = max_retries
        self.step_timeout = step_timeout
        self.active_contexts: Dict[str, ExecutionContext] = {}

    def create_context(self, session_id: str, websocket: Any) -> ExecutionContext:
        """Create execution context for a session."""
        context = ExecutionContext(session_id=session_id, websocket=websocket)
        self.active_contexts[session_id] = context
        return context

    def get_context(self, session_id: str) -> Optional[ExecutionContext]:
        """Get execution context by session ID."""
        return self.active_contexts.get(session_id)

    def remove_context(self, session_id: str):
        """Remove execution context."""
        self.active_contexts.pop(session_id, None)

    # TODO: Replaced by new Perception Controller (see UI Perception Blueprint)
    # Legacy UI snapshot request removed - executors should not request UI data
    # directly. Perception Controller must provide perception data before execution.
    async def request_ui_snapshot(
        self, context: ExecutionContext
    ) -> Optional[Dict[str, Any]]:
        """Request UI snapshot - removed, Perception Controller must provide data."""
        logger.warning("UI snapshot request removed - Perception Controller must provide data")
        return None

    async def execute_step(
        self, context: ExecutionContext, step_id: str, action: Dict[str, Any]
    ) -> StepResult:
        """
        Execute a single step and wait for result.

        Args:
            context: Execution context
            step_id: Unique step identifier
            action: Action to execute (type, coordinates, text, etc.)

        Returns:
            StepResult with success/failure and UI state after
        """
        start_time = time.time()

        try:
            # Create future to wait for result
            context.pending_step_result = asyncio.get_running_loop().create_future()

            # Send execute command
            await context.websocket.send_json(
                {"type": "execute_step", "step_id": step_id, "action": action}
            )
            logger.info(f"⚡ Sent step {step_id}: {action.get('type', 'unknown')}")

            # Wait for result with timeout
            result_data = await asyncio.wait_for(
                context.pending_step_result, timeout=self.step_timeout
            )

            duration_ms = (time.time() - start_time) * 1000

            result = StepResult(
                step_id=step_id,
                success=result_data.get("success", False),
                error=result_data.get("error"),
                ui_after=None,  # TODO: UI state tracking removed - Perception Controller handles this
                duration_ms=duration_ms,
            )

            # TODO: UI state tracking removed - Perception Controller must handle
            # perception data, not executors

            context.steps_executed.append(result)

            logger.info(
                f"{'✅' if result.success else '❌'} Step {step_id} completed in {duration_ms:.0f}ms"
            )
            return result

        except asyncio.TimeoutError:
            duration_ms = (time.time() - start_time) * 1000
            result = StepResult(
                step_id=step_id,
                success=False,
                error="Step execution timed out",
                duration_ms=duration_ms,
            )
            context.steps_executed.append(result)
            logger.warning(f"⏱️ Step {step_id} timed out after {duration_ms:.0f}ms")
            return result
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            result = StepResult(
                step_id=step_id, success=False, error=str(e), duration_ms=duration_ms
            )
            context.steps_executed.append(result)
            logger.error(f"❌ Step {step_id} failed: {e}")
            return result
        finally:
            context.pending_step_result = None

    def handle_ui_snapshot(self, session_id: str, ui_data: Dict[str, Any]):
        """
        Handle incoming UI snapshot from Android.

        Called by WebSocket router when ui_snapshot message is received.
        """
        context = self.get_context(session_id)
        if (
            context
            and context.pending_ui_snapshot
            and not context.pending_ui_snapshot.done()
        ):
            context.pending_ui_snapshot.set_result(ui_data)

    def handle_step_result(self, session_id: str, result_data: Dict[str, Any]):
        """
        Handle incoming step result from Android.

        Called by WebSocket router when step_result message is received.
        """
        context = self.get_context(session_id)
        if (
            context
            and context.pending_step_result
            and not context.pending_step_result.done()
        ):
            context.pending_step_result.set_result(result_data)

    async def execute_plan(
        self,
        context: ExecutionContext,
        plan: List[Dict[str, Any]],
        verify_callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """
        Execute a full action plan with verification.

        Args:
            context: Execution context
            plan: List of action steps
            verify_callback: Optional callback to verify each step

        Returns:
            Execution summary with results
        """
        logger.info(f"🚀 Starting plan execution: {len(plan)} steps")

        results = []
        total_steps = len(plan)
        successful_steps = 0

        for i, step in enumerate(plan):
            step_id = str(step.get("step", i + 1))
            action_type = step.get("action", step.get("type", "unknown"))

            # Build action payload
            action = {"type": action_type}

            if action_type in ["tap", "click"]:
                coords = step.get("coordinates", [])
                if coords and len(coords) >= 2:
                    action["x"] = coords[0]
                    action["y"] = coords[1]

            elif action_type == "swipe":
                coords = step.get("coordinates", [])
                if len(coords) >= 4:
                    action["x1"] = coords[0]
                    action["y1"] = coords[1]
                    action["x2"] = coords[2]
                    action["y2"] = coords[3]
                action["duration"] = step.get("duration", 300)

            elif action_type in ["type", "text_input", "input"]:
                action["text"] = step.get("text", "")

            elif action_type in ["scroll_up", "scroll_down", "back", "home"]:
                pass  # No additional params needed

            # Execute with retry logic
            retries = 0
            max_retries = step.get("max_retries", self.max_retries)
            result = None

            while retries <= max_retries:
                result = await self.execute_step(context, step_id, action)

                if result.success:
                    successful_steps += 1
                    break

                retries += 1
                if retries <= max_retries:
                    logger.info(f"🔄 Retrying step {step_id} ({retries}/{max_retries})")
                    await asyncio.sleep(0.5)  # Brief pause before retry

            results.append(
                {
                    "step_id": step_id,
                    "action": action_type,
                    "success": result.success if result else False,
                    "error": result.error if result else "No result",
                    "retries": retries,
                    "duration_ms": result.duration_ms if result else 0,
                }
            )

            # Stop on failure if not retriable
            if result and not result.success and retries > max_retries:
                logger.warning(
                    f"⚠️ Plan execution stopped at step {step_id} after {retries} retries"
                )
                break

            # Optional verification
            if verify_callback and result and result.success:
                verified = await verify_callback(context, step, result)
                if not verified:
                    logger.warning(f"⚠️ Step {step_id} verification failed")

        total_duration = (time.time() - context.start_time) * 1000

        summary = {
            "total_steps": total_steps,
            "successful_steps": successful_steps,
            "failed_steps": total_steps - successful_steps,
            "success_rate": successful_steps / total_steps if total_steps > 0 else 0,
            "total_duration_ms": total_duration,
            "steps": results,
        }

        logger.info(
            f"📊 Plan execution complete: {successful_steps}/{total_steps} steps succeeded in {total_duration:.0f}ms"
        )

        return summary


# Global instance
step_executor = StepExecutor()


def get_step_executor() -> StepExecutor:
    """Get the global step executor instance."""
    return step_executor
