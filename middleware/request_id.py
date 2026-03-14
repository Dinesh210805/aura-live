"""Request ID middleware with logging."""

import secrets
import time

from fastapi import Request

from constants import REQUEST_ID_HEADER
from utils.logger import get_logger
from utils.unified_logger import get_unified_logger

logger = get_logger(__name__)
unified_logger = get_unified_logger()


async def add_request_id(request: Request, call_next):
    """Add unique request ID and log request/response."""
    request_id = request.headers.get(REQUEST_ID_HEADER, secrets.token_urlsafe(16))
    request.state.request_id = request_id
    
    start = time.perf_counter()
    method = request.method
    path = request.url.path
    
    try:
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        
        # Log all non-health requests
        if "/health" not in path:
            logger.info(f"[{request_id[:8]}] {method} {path} → {response.status_code} ({duration_ms:.0f}ms)")
            
            # Add to unified logger
            unified_logger.add(
                message=f"{method} {path} → {response.status_code} ({duration_ms:.0f}ms)",
                level="INFO",
                source="http",
                request_id=request_id,
                context={"method": method, "path": path, "status": response.status_code, "duration_ms": duration_ms}
            )
        
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
        
    except Exception as e:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.error(f"[{request_id[:8]}] {method} {path} → ERROR ({duration_ms:.0f}ms): {e}", exc_info=True)
        
        # Add to unified logger
        unified_logger.add(
            message=f"{method} {path} → ERROR: {str(e)[:200]}",
            level="ERROR",
            source="http",
            request_id=request_id,
            context={"method": method, "path": path, "duration_ms": duration_ms, "error": str(e)}
        )
        raise
