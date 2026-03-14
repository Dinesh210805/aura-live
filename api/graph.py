"""Graph information endpoint."""

from functools import lru_cache
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from aura_graph.graph import get_graph_info
from middleware.rate_limit import limiter
from utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/graph/info")
@limiter.limit("30/minute")
@lru_cache(maxsize=1)
async def get_graph_information(request: Request) -> Dict[str, Any]:
    """
    Get cached graph configuration information.

    Returns:
        Graph configuration details
    """
    try:
        graph_info = get_graph_info()
        return graph_info

    except Exception as e:
        logger.error(f"Failed to get graph info: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve graph information",
        )
