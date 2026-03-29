"""
web_search_node — executes a Tavily web search and stores the answer.

Invoked when the Commander classifies action="web_search" (or aliases).
The result is placed in `feedback_message` so the speak node reads it
via TTS — no extra plumbing required.
"""

import re

from utils.logger import get_logger

from ..state import TaskState

logger = get_logger(__name__)

# Detect news-flavoured queries so Tavily uses its news index.
_NEWS_RE = re.compile(
    r"\b(?:news|latest|recent|today(?:'s)?|headlines|breaking|current\s+events"
    r"|what(?:'s| is)\s+(?:happening|going\s+on))\b",
    re.IGNORECASE,
)


async def web_search_node(state: TaskState) -> dict:
    """Search the web and return the answer as feedback_message."""
    from services.web_search import get_web_search_service
    from services.task_progress import get_task_progress_service

    intent = state.get("intent") or {}
    # `content` holds the query when Commander sets action="web_search".
    # Fall back to the raw transcript if content is missing.
    query = (
        intent.get("content")
        or state.get("transcript")
        or state.get("streaming_transcript")
        or ""
    ).strip()

    if not query:
        return {
            "status": "web_search_failed",
            "feedback_message": "I didn't catch what you wanted me to search for.",
        }

    topic = "news" if _NEWS_RE.search(query) else "general"
    get_task_progress_service().emit_agent_status(
        "WebSearch", f"Searching: '{query[:50]}'"
    )
    logger.info(f"web_search_node: query='{query[:60]}' topic={topic}")

    service = get_web_search_service()
    answer = await service.search(query, topic=topic)

    return {
        "status": "web_search_complete",
        "feedback_message": answer,
    }
