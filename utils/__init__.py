"""
Utilities package for AURA backend.

This package contains utility modules including types, logger, exceptions,
circuit breaker, fuzzy classifier, audio utilities, and instruction types.
"""

from .exceptions import (
    ActionTimeoutError,
    AgentExecutionError,
    AURAAutomationError,
    AuraBaseException,
    AuthenticationError,
    ConfigurationError,
    DeviceConnectionError,
    ExecutionError,
    ModelProviderError,
    NetworkTimeoutError,
    RetryExhaustedError,
    ServiceError,
    StateValidationError,
    UIInteractionError,
)
from .logger import get_logger
from .types import ActionResult, IntentObject, UIElement
from .ui_element_finder import (
    find_element,
    find_editable_element,
    find_scrollable_element,
    validate_coordinates,
    adjust_to_safe_zone,
    get_element_center,
)

__all__ = [
    # Types
    "IntentObject",
    "UIElement",
    "ActionResult",
    # Logger
    "get_logger",
    # UI Element Finder
    "find_element",
    "find_editable_element",
    "find_scrollable_element",
    "validate_coordinates",
    "adjust_to_safe_zone",
    "get_element_center",
    # Exceptions
    "AuraBaseException",
    "ConfigurationError",
    "ModelProviderError",
    "AgentExecutionError",
    "DeviceConnectionError",
    "UIInteractionError",
    "ActionTimeoutError",
    "AuthenticationError",
    "StateValidationError",
    "AURAAutomationError",
    "ExecutionError",
    "RetryExhaustedError",
    "NetworkTimeoutError",
    "ServiceError",
]
