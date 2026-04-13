"""
REST fallback endpoint for natural-language Android task execution.

POST /api/v1/execute — run any utterance through the full AURA pipeline.
Agents without MCP support can POST here instead of connecting via MCP protocol.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


class ExecuteRequest(BaseModel):
    command: str
    """Natural-language command, e.g. 'Open Spotify and play Liked Songs'."""
    source: str = "api"
    """Caller identifier — logged as command_source in TaskState."""


class ExecuteResponse(BaseModel):
    success: bool
    response_text: str
    steps_taken: int
    error: Optional[str] = None
    log_path: Optional[str] = None
    """Local path to the HTML execution log for this run."""


@router.post("/execute", response_model=ExecuteResponse)
async def execute_task(body: ExecuteRequest, request: Request) -> ExecuteResponse:
    """
    Execute a natural-language Android command through the full AURA pipeline.

    The request goes through: intent parsing → perception → planning →
    gesture execution → natural-language response generation.

    Returns the spoken response and execution summary.
    """
    if not body.command.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="command must not be empty",
        )

    graph_app = getattr(request.app.state, "graph_app", None)
    if graph_app is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AURA graph is not initialised — server may still be starting up",
        )

    try:
        from aura_graph.graph import execute_aura_task_from_text

        result = await execute_aura_task_from_text(
            app=graph_app,
            text_input=body.command,
            thread_id=f"api-{body.source}",
            track_workflow=False,
        )
    except Exception as exc:
        logger.exception("execute_task failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )

    succeeded = result.get("status") not in ("failed", "error")
    response_text = (
        result.get("spoken_response")
        or result.get("feedback_message")
        or ("Task completed." if succeeded else "Task failed.")
    )

    return ExecuteResponse(
        success=succeeded,
        response_text=response_text,
        steps_taken=len(result.get("executed_steps", [])),
        error=result.get("error_message") if not succeeded else None,
        log_path=result.get("local_log_path"),
    )
