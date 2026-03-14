"""Sensitive action policy management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

from middleware.auth import verify_api_key
from middleware.rate_limit import limiter
from utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


class SensitiveCheckRequest(BaseModel):
    """Request to check if a command is sensitive."""
    command: str
    intent: Optional[str] = None


class AddKeywordRequest(BaseModel):
    """Request to add a custom sensitive keyword."""
    category: str
    keyword: str


@router.post("/sensitive-policy/check")
async def check_sensitive_action(request_body: SensitiveCheckRequest, request: Request):
    """
    Check if a command contains sensitive actions.
    
    Args:
        request: Command to check
        
    Returns:
        Detection result
    """
    from policies.sensitive_actions import sensitive_action_policy
    
    is_sensitive, reason = sensitive_action_policy.is_sensitive(
        request_body.command, request_body.intent
    )
    
    if is_sensitive:
        blocked_response = sensitive_action_policy.get_blocked_response(
            reason, request_body.command
        )
        return {
            "is_sensitive": True,
            "reason": reason,
            "message": blocked_response["message"],
            "would_block": True
        }
    
    return {
        "is_sensitive": False,
        "reason": None,
        "would_block": False
    }


@router.get("/sensitive-policy/stats")
@limiter.limit("30/minute")
async def get_policy_stats(request: Request):
    """Get statistics about the sensitive action policy."""
    from policies.sensitive_actions import sensitive_action_policy
    
    return sensitive_action_policy.get_stats()


@router.post("/sensitive-policy/keywords/add")
@limiter.limit("10/minute")
async def add_custom_keyword(
    request_body: AddKeywordRequest,
    request: Request,
    api_key: str = Depends(verify_api_key),
):
    """
    Add a custom sensitive keyword to a category.
    
    Args:
        request: Category and keyword to add
        
    Returns:
        Success status
    """
    from policies.sensitive_actions import sensitive_action_policy
    
    valid_categories = ["banking", "shutdown", "destructive", "security", "permission", "apps"]
    
    if request_body.category not in valid_categories:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category. Must be one of: {', '.join(valid_categories)}"
        )
    
    success = sensitive_action_policy.add_custom_keyword(
        request_body.category, request_body.keyword
    )
    
    if success:
        return {
            "success": True,
            "message": f"Added '{request_body.keyword}' to {request_body.category} category"
        }
    else:
        return {
            "success": False,
            "message": "Failed to add keyword (may already exist)"
        }


@router.post("/sensitive-policy/toggle")
@limiter.limit("5/minute")
async def toggle_policy(
    enabled: bool,
    request: Request,
    api_key: str = Depends(verify_api_key),
):
    """
    Enable or disable the sensitive action policy.
    
    Args:
        enabled: Whether to enable the policy
        
    Returns:
        New status
    """
    from policies.sensitive_actions import sensitive_action_policy
    
    sensitive_action_policy.enabled = enabled
    
    return {
        "enabled": sensitive_action_policy.enabled,
        "message": f"Sensitive action policy {'enabled' if enabled else 'disabled'}"
    }


@router.get("/sensitive-policy/keywords")
@limiter.limit("30/minute")
async def list_all_keywords(request: Request):
    """List all sensitive keywords by category."""
    from policies.sensitive_actions import sensitive_action_policy
    
    return {
        "banking": sensitive_action_policy.BANKING_KEYWORDS,
        "shutdown": sensitive_action_policy.SYSTEM_SHUTDOWN_KEYWORDS,
        "destructive": sensitive_action_policy.DESTRUCTIVE_KEYWORDS,
        "security": sensitive_action_policy.SECURITY_KEYWORDS,
        "permission": sensitive_action_policy.PERMISSION_KEYWORDS,
        "sensitive_apps": sensitive_action_policy.SENSITIVE_APPS,
    }
