"""Authentication middleware."""

import secrets
from typing import Annotated

from fastapi import Header, HTTPException, status

from config.settings import get_settings
from utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


def verify_api_key(x_api_key: Annotated[str, Header()] = None) -> str:
    """
    Verify API key for device endpoints.

    Args:
        x_api_key: API key from request header

    Returns:
        Validated API key

    Raises:
        HTTPException: If API key is invalid
    """
    if not settings.require_api_key:
        return "development-mode"

    expected_key = getattr(settings, "device_api_key", None)
    if not expected_key:
        logger.error("No device API key configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server configuration error",
        )

    if not x_api_key or not secrets.compare_digest(x_api_key, expected_key):
        logger.warning("Invalid API key attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return x_api_key
