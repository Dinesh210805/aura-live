"""
AURA ADK Agent — wraps the LangGraph execution pipeline as a Google ADK FunctionTool.

Satisfies the "Use Google GenAI SDK or ADK" eligibility requirement for the
Gemini Live Agent Challenge without modifying any existing agent or graph logic.

Architecture:
    ADK root_agent (gemini-2.5-flash)
        └── execute_aura_task (FunctionTool)
                └── execute_aura_task_from_text()  ← existing LangGraph entry point
                        └── 9-agent LangGraph state machine

Lazy graph initialisation:
    The compiled LangGraph app is set by main.py lifespan via set_compiled_graph()
    AFTER compile_aura_graph() completes. This avoids circular imports between
    adk_agent.py and the services that compile_aura_graph() initialises.

Verification:
    python -c "from adk_agent import root_agent; print(root_agent.name)"
    # Expected output: AURA
"""

import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy reference to the compiled LangGraph app
# ---------------------------------------------------------------------------

_compiled_graph: Optional[Any] = None


def set_compiled_graph(app: Any) -> None:
    """
    Store the compiled LangGraph application.

    Called from main.py lifespan after compile_aura_graph() completes.
    Must be called before execute_aura_task() is invoked.

    Args:
        app: The compiled LangGraph StateGraph application.
    """
    global _compiled_graph
    _compiled_graph = app
    logger.info("ADK agent: compiled LangGraph graph registered")


def _get_graph() -> Any:
    """Return the compiled graph or raise a clear error if not initialised."""
    if _compiled_graph is None:
        raise RuntimeError(
            "AURA LangGraph has not been compiled yet. "
            "Ensure set_compiled_graph() is called during server startup "
            "before any ADK tool invocation."
        )
    return _compiled_graph


# ---------------------------------------------------------------------------
# ADK FunctionTool implementation
# ---------------------------------------------------------------------------


async def execute_aura_task(command: str, session_id: str = "adk-session") -> dict:
    """
    Execute a UI navigation task on the connected Android device.

    Invokes the full AURA LangGraph pipeline:
        perceive → plan → act → verify

    This function is registered as a Google ADK FunctionTool. The ADK
    framework automatically converts its signature into a Gemini tool schema,
    so parameter names, types, and the docstring are all part of the contract.

    Args:
        command: Natural language navigation command.
                 Example: "Open Spotify and play my liked songs"
        session_id: Active device session identifier used for conversation
                    continuity. Defaults to 'adk-session'.

    Returns:
        A dict with:
            success (bool): True when the task completed without errors.
            response (str): Natural language summary to read aloud to the user.
            steps_taken (int): Number of gesture steps executed on the device.
            execution_log_url (str | None): Public GCS URL of the execution
                log, or None when GCS uploads are disabled.
    """
    from aura_graph.graph import execute_aura_task_from_text

    graph = _get_graph()

    try:
        result = await execute_aura_task_from_text(
            app=graph,
            text_input=command,
            thread_id=session_id,
            track_workflow=True,
        )
    except Exception as exc:
        logger.error(f"ADK execute_aura_task failed: {exc}", exc_info=True)
        return {
            "success": False,
            "response": f"Task failed with an internal error: {exc}",
            "steps_taken": 0,
            "execution_log_url": None,
        }

    succeeded = result.get("status") not in ("failed", "error")
    spoken = (
        result.get("spoken_response")
        or result.get("feedback_message")
        or ("Task completed." if succeeded else "Task failed.")
    )

    return {
        "success": succeeded,
        "response": spoken,
        "steps_taken": len(result.get("executed_steps", [])),
        "execution_log_url": result.get("log_url"),
    }


# ---------------------------------------------------------------------------
# ADK Agent definition
# ---------------------------------------------------------------------------

# Guard import so the module can be imported even if google-adk is not yet
# installed, e.g. during CI or when only running the existing test suite.
try:
    from google.adk import Agent
    from google.adk.tools import FunctionTool

    aura_tool = FunctionTool(func=execute_aura_task)

    root_agent = Agent(
        name="AURA",
        model="gemini-2.5-flash",
        description=(
            "AURA — Autonomous User-Responsive Agent. "
            "Controls Android devices via natural language. "
            "Sees the screen, plans multi-step actions, and executes precise gestures."
        ),
        instruction="""
You are AURA, an autonomous Android UI navigation agent.

When the user gives a command to control their device, call execute_aura_task
immediately with the full natural-language command. Do NOT paraphrase or
split compound commands — pass the entire instruction so AURA's planner can
decompose it correctly.

Confirmation policy — ask the user ONLY for these sensitive action types:
  • Sending messages or emails to contacts
  • Making purchases or entering payment details
  • Permanently deleting files, accounts, or data
  • Posting publicly to social media
For all other navigation actions, proceed without confirmation.

After execute_aura_task returns:
  • If success=true: summarise what happened in one or two sentences.
  • If success=false: explain what was attempted, then suggest a simpler
    rephrasing or alternative command the user can try.

Personality: helpful, concise, and slightly warm — never robotic.
Always identify yourself as AURA. Never claim to be a human or a general AI.
""",
        tools=[aura_tool],
    )

    logger.info("ADK root_agent initialised (model=gemini-2.5-flash)")

except ImportError as _adk_import_error:
    # google-adk not installed — define stubs so the rest of the codebase can
    # still import this module without crashing.
    logger.warning(
        f"google-adk not installed; ADK agent is unavailable. "
        f"Run: pip install google-adk  ({_adk_import_error})"
    )
    aura_tool = None  # type: ignore[assignment]
    root_agent = None  # type: ignore[assignment]
