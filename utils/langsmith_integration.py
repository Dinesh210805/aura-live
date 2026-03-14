"""
LangSmith Integration - Auto-link traces to unified logger.

Captures LangSmith run IDs and generates links automatically.
"""

import os
from typing import Optional
from langsmith import traceable
from utils.logger import get_logger

logger = get_logger(__name__)

# Get LangSmith project from env
LANGSMITH_PROJECT = os.getenv("LANGCHAIN_PROJECT", "aura-agent-visualization")


def get_langsmith_url(run_id: str, project: str = None) -> str:
    """
    Generate LangSmith URL for a run.
    
    Args:
        run_id: LangSmith run ID
        project: Project ID (UUID format, defaults to env variable)
    
    Returns:
        Public LangSmith URL
    """
    project_id = project or os.getenv("LANGCHAIN_PROJECT_ID") or os.getenv("LANGCHAIN_PROJECT", "aura-agent-visualization")
    
    # LangSmith public URL format: https://smith.langchain.com/public/{project-id}/r/{run-id}
    # If project looks like a name rather than UUID, try to construct URL anyway
    return f"https://smith.langchain.com/public/{project_id}/r/{run_id}"


def log_langsmith_trace(
    trace_id: str,
    run_id: str,
    description: str = "LangSmith trace",
    project: str = None
):
    """
    Log LangSmith trace link to unified logger.
    
    Args:
        trace_id: Your internal trace ID
        run_id: LangSmith run ID
        description: Description of what this trace captured
        project: LangSmith project name
    """
    try:
        from utils.unified_logger import get_unified_logger
        
        url = get_langsmith_url(run_id, project)
        unified = get_unified_logger()
        
        unified.add(
            message=description,
            level="INFO",
            source="langsmith",
            trace_id=trace_id,
            langsmith_url=url,
            context={
                "run_id": run_id,
                "project": project or LANGSMITH_PROJECT
            }
        )
        
        logger.debug(f"🔗 LangSmith trace: {url}")
        
    except Exception as e:
        logger.debug(f"Could not log LangSmith trace: {e}")


def capture_langsmith_context():
    """
    Get current LangSmith run context.
    
    Returns dict with run_id if available.
    """
    try:
        from langsmith import get_current_run_tree
        
        run_tree = get_current_run_tree()
        if run_tree:
            return {
                "run_id": str(run_tree.id),
                "name": run_tree.name,
                "parent_run_id": str(run_tree.parent_run_id) if run_tree.parent_run_id else None,
            }
    except Exception:
        pass
    
    return {}
