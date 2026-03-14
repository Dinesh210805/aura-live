"""Global exception handlers."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from utils.exceptions import AuraBaseException, ConfigurationError
from utils.logger import get_logger
from utils.unified_logger import get_unified_logger

logger = get_logger(__name__)
unified_logger = get_unified_logger()


def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers."""

    @app.exception_handler(AuraBaseException)
    async def aura_exception_handler(request: Request, exc: AuraBaseException):
        """Handle AURA-specific exceptions."""
        req_id = getattr(request.state, "request_id", "unknown")[:8]
        logger.error(f"[{req_id}] AURA exception: {exc}", exc_info=True)
        
        # Add to unified logger
        unified_logger.add(
            message=f"AURA exception: {type(exc).__name__}: {str(exc)[:200]}",
            level="ERROR",
            source="exception",
            request_id=req_id,
            context={"exception_type": type(exc).__name__, "error": str(exc)}
        )
        
        return JSONResponse(
            status_code=400, content={"error": str(exc), "type": type(exc).__name__}
        )

    @app.exception_handler(ConfigurationError)
    async def config_exception_handler(request: Request, exc: ConfigurationError):
        """Handle configuration exceptions."""
        req_id = getattr(request.state, "request_id", "unknown")[:8]
        logger.error(f"[{req_id}] Configuration error: {exc}", exc_info=True)
        
        # Add to unified logger
        unified_logger.add(
            message=f"Configuration error: {str(exc)[:200]}",
            level="ERROR",
            source="exception",
            request_id=req_id,
            context={"exception_type": "ConfigurationError", "error": str(exc)}
        )
        
        return JSONResponse(
            status_code=500,
            content={"error": "Configuration error", "type": "ConfigurationError"},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        """Handle unexpected exceptions with full stack trace."""
        req_id = getattr(request.state, "request_id", "unknown")[:8]
        logger.exception(f"[{req_id}] Unhandled exception: {exc}")
        
        # Add to unified logger
        unified_logger.add(
            message=f"Unhandled exception: {type(exc).__name__}: {str(exc)[:200]}",
            level="ERROR",
            source="exception",
            request_id=req_id,
            context={"exception_type": type(exc).__name__, "error": str(exc)}
        )
        
        return JSONResponse(
            status_code=500, content={"error": "Internal server error", "type": "InternalError"}
        )
