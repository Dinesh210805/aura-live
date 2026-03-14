"""Health check endpoints."""

import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from config.settings import get_settings
from constants import API_VERSION
from middleware.rate_limit import limiter
from utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()
router = APIRouter()


class HITLTestRequest(BaseModel):
    """Request body for HITL test endpoint."""
    question_type: str = "confirmation"  # confirmation, single_choice, text_input, notification, action_required
    title: str = "Test Dialog"
    message: str = "This is a test HITL dialog"
    options: Optional[list] = None
    timeout: float = 30.0


@router.post("/test/hitl")
async def test_hitl(request: HITLTestRequest) -> Dict[str, Any]:
    """
    Test HITL (Human-in-the-Loop) dialog.
    
    Sends a HITL question to connected Android apps and waits for response.
    
    Args:
        request: HITL test configuration
        
    Returns:
        User's response or timeout status
    """
    try:
        from services.hitl_service import get_hitl_service
        hitl_service = get_hitl_service()
        
        logger.info(f"🧪 Testing HITL: type={request.question_type}, title={request.title}")
        
        if request.question_type == "confirmation":
            result = await hitl_service.ask_confirmation(
                message=request.message,
                title=request.title,
                timeout=request.timeout
            )
            return {"success": True, "confirmed": result}
            
        elif request.question_type == "single_choice":
            options = request.options or ["Option A", "Option B", "Option C"]
            result = await hitl_service.ask_choice(
                message=request.message,
                options=options,
                title=request.title,
                timeout=request.timeout
            )
            return {"success": True, "selected_option": result}
            
        elif request.question_type == "text_input":
            result = await hitl_service.ask_text_input(
                message=request.message,
                title=request.title,
                timeout=request.timeout
            )
            return {"success": True, "text_input": result}
            
        elif request.question_type == "notification":
            result = await hitl_service.notify(
                message=request.message,
                title=request.title,
                timeout=request.timeout
            )
            return {"success": True, "acknowledged": result}
            
        elif request.question_type == "action_required":
            result = await hitl_service.wait_for_user_action(
                message=request.message,
                title=request.title,
                action_type="biometric_unlock",
                timeout=request.timeout
            )
            return {"success": True, "action_completed": result}
            
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown question_type: {request.question_type}"
            )
            
    except Exception as e:
        logger.error(f"HITL test failed: {e}")
        return {"success": False, "error": str(e)}


@router.get("/health")
@limiter.limit("60/minute")
async def health_check(request: Request) -> Dict[str, Any]:
    """
    Comprehensive health check with dependency verification.

    Returns:
        Health status with service details
    """
    try:
        from main import graph_app

        services = {}

        # Check graph application
        try:
            services["graph"] = "healthy" if graph_app else "unhealthy"
        except Exception as e:
            logger.error(f"Graph health check failed: {e}")
            services["graph"] = f"unhealthy: {str(e)}"

        # Check accessibility service
        try:
            from services.real_accessibility import real_accessibility_service

            services["accessibility"] = (
                "healthy" if real_accessibility_service else "unhealthy"
            )
        except Exception as e:
            logger.error(f"Accessibility health check failed: {e}")
            services["accessibility"] = f"unhealthy: {str(e)}"

        # Check API keys configuration
        services["auth"] = (
            "configured"
            if getattr(settings, "device_api_key", None)
            else "not_configured"
        )

        overall_status = (
            "healthy"
            if all("healthy" in str(s) for s in services.values())
            else "degraded"
        )

        return {
            "status": overall_status,
            "version": "1.0.0",
            "api_version": API_VERSION,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "services": services,
            "environment": settings.environment,
        }

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Health check failed",
        )
