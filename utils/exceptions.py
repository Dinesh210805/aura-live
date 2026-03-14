"""
Custom exception classes for the AURA backend.

This module defines specific exception types that provide clear error
handling and better debugging information throughout the application.
"""

from typing import Any, Dict, Optional


class AuraBaseException(Exception):
    """
    Base exception class for all AURA-specific exceptions.

    This provides a consistent interface and additional context
    for all custom exceptions in the application.
    """

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Initialize the base exception.

        Args:
            message: Human-readable error message.
            error_code: Optional error code for programmatic handling.
            context: Additional context information about the error.
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.context = context or {}

    def __str__(self) -> str:
        """Return a string representation of the exception."""
        result = self.message
        if self.error_code:
            result = f"[{self.error_code}] {result}"
        if self.context:
            result += f" | Context: {self.context}"
        return result


class ServiceError(AuraBaseException):
    """
    Exception raised when a service operation fails.

    This exception is used for general service failures that don't
    fit into more specific categories.
    """

    def __init__(
        self,
        message: str,
        service_name: Optional[str] = None,
        operation: Optional[str] = None,
        error_code: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Initialize the service error.

        Args:
            message: Error message.
            service_name: Name of the service that failed.
            operation: The operation that was being performed.
            error_code: Optional error code.
            context: Additional context information.
        """
        super().__init__(message, error_code, context)
        self.service_name = service_name
        self.operation = operation


class ConfigurationError(AuraBaseException):
    """
    Exception raised for configuration-related errors.

    This includes missing required settings, invalid configuration values,
    or misconfigured dependencies.
    """

    def __init__(self, message: str, config_key: Optional[str] = None):
        """
        Initialize configuration error.

        Args:
            message: Error message describing the configuration issue
            config_key: Optional key of the problematic configuration
        """
        self.config_key = config_key
        super().__init__(message)


class ModelProviderError(AuraBaseException):
    """
    Exception raised for model provider errors.

    This includes API errors, rate limiting, model unavailability,
    or provider authentication issues.
    """

    def __init__(
        self,
        message: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        error_code: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize model provider error.

        Args:
            message: Error message describing the provider issue
            provider: Name of the provider (e.g., 'groq', 'gemini')
            model: Name of the model if applicable
            error_code: Optional error code for programmatic handling
            context: Additional context information
        """
        self.provider = provider
        self.model = model
        super().__init__(message, error_code, context)


class DeviceConnectionError(AuraBaseException):
    """
    Exception raised for device connection errors.

    This includes device registration failures, disconnection issues,
    or communication problems with the Android device.
    """

    def __init__(self, message: str, device_id: Optional[str] = None):
        """
        Initialize device connection error.

        Args:
            message: Error message describing the connection issue
            device_id: Optional device identifier
        """
        self.device_id = device_id
        super().__init__(message)


class AgentExecutionError(AuraBaseException):
    """
    Exception raised when CrewAI agent execution fails.

    This includes task failures, tool errors, and agent-specific issues.
    """

    def __init__(
        self,
        message: str,
        agent_name: str,
        task_description: Optional[str] = None,
        error_code: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Initialize agent execution error.

        Args:
            message: Human-readable error message.
            agent_name: Name of the agent that failed.
            task_description: Description of the task being executed.
            error_code: Optional error code.
            context: Additional context about the failure.
        """
        context = context or {}
        context.update({"agent_name": agent_name})
        if task_description:
            context["task_description"] = task_description

        super().__init__(message, error_code, context)
        self.agent_name = agent_name
        self.task_description = task_description


class UIInteractionError(AuraBaseException):
    """
    Exception raised for UI interaction errors.

    This includes gesture execution failures, element not found errors,
    or coordinate validation issues.
    """

    def __init__(
        self, message: str, action: Optional[str] = None, element: Optional[str] = None
    ):
        """
        Initialize UI interaction error.

        Args:
            message: Error message describing the interaction issue
            action: Type of action that failed
            element: Element that couldn't be interacted with
        """
        self.action = action
        self.element = element
        super().__init__(message)


class ActionTimeoutError(AuraBaseException):
    """
    Exception raised when an action times out.

    This includes execution timeouts, network timeouts,
    or any operation that exceeds its time limit.
    """

    def __init__(self, message: str, timeout_seconds: Optional[float] = None):
        """
        Initialize action timeout error.

        Args:
            message: Error message describing the timeout
            timeout_seconds: Duration that was exceeded
        """
        self.timeout_seconds = timeout_seconds
        super().__init__(message)


class AuthenticationError(AuraBaseException):
    """
    Exception raised for authentication failures.

    This includes invalid API keys, expired tokens,
    or insufficient permissions.
    """

    def __init__(self, message: str, auth_type: Optional[str] = None):
        """
        Initialize authentication error.

        Args:
            message: Error message describing the auth issue
            auth_type: Type of authentication that failed
        """
        self.auth_type = auth_type
        super().__init__(message)


class StateValidationError(AuraBaseException):
    """
    Exception raised when LangGraph state validation fails.

    This includes invalid state transitions, missing required state data,
    and state consistency issues.
    """

    def __init__(
        self,
        message: str,
        state_key: Optional[str] = None,
        node_name: Optional[str] = None,
        error_code: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Initialize state validation error.

        Args:
            message: Human-readable error message.
            state_key: Name of the problematic state key.
            node_name: Name of the node where the error occurred.
            error_code: Optional error code.
            context: Additional context about the failure.
        """
        context = context or {}
        if state_key:
            context["state_key"] = state_key
        if node_name:
            context["node_name"] = node_name

        super().__init__(message, error_code, context)
        self.state_key = state_key
        self.node_name = node_name


class AURAAutomationError(AuraBaseException):
    """
    Exception raised when AURA automation operations fail.

    This covers errors in the enhanced automation orchestrator,
    intent-based automation, and visual monitoring systems.
    """

    def __init__(
        self,
        message: str,
        automation_type: Optional[str] = None,
        strategy_used: Optional[str] = None,
        error_code: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Initialize automation error.

        Args:
            message: Human-readable error message.
            automation_type: Type of automation that failed (intent, accessibility, hybrid, etc.).
            strategy_used: Strategy that was being used when the error occurred.
            error_code: Optional error code.
            context: Additional context about the failure.
        """
        context = context or {}
        if automation_type:
            context["automation_type"] = automation_type
        if strategy_used:
            context["strategy_used"] = strategy_used

        super().__init__(message, error_code, context)
        self.automation_type = automation_type
        self.strategy_used = strategy_used


class ExecutionError(AuraBaseException):
    """
    Exception raised when command or action execution fails.

    This is a generic execution error for operations that fail
    during the execution phase but don't fit other specific categories.
    """

    def __init__(
        self,
        message: str,
        operation: Optional[str] = None,
        exit_code: Optional[int] = None,
        error_code: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Initialize execution error.

        Args:
            message: Human-readable error message.
            operation: The operation that failed to execute.
            exit_code: Exit code from the failed operation (if applicable).
            error_code: Optional error code.
            context: Additional context about the execution failure.
        """
        context = context or {}
        if operation:
            context["operation"] = operation
        if exit_code is not None:
            context["exit_code"] = exit_code

        super().__init__(message, error_code, context)
        self.operation = operation
        self.exit_code = exit_code


class RetryExhaustedError(AuraBaseException):
    """
    Exception raised when retry attempts have been exhausted.

    This exception is used when an operation has been retried
    the maximum number of times and still fails.
    """

    def __init__(
        self,
        message: str,
        operation: Optional[str] = None,
        max_retries: Optional[int] = None,
        last_error: Optional[Exception] = None,
        error_code: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Initialize retry exhausted error.

        Args:
            message: Human-readable error message.
            operation: The operation that exhausted retries.
            max_retries: Maximum number of retries that were attempted.
            last_error: The last error that occurred before giving up.
            error_code: Optional error code.
            context: Additional context about the retry failure.
        """
        context = context or {}
        if operation:
            context["operation"] = operation
        if max_retries is not None:
            context["max_retries"] = max_retries
        if last_error:
            context["last_error"] = str(last_error)

        super().__init__(message, error_code, context)
        self.operation = operation
        self.max_retries = max_retries
        self.last_error = last_error


class NetworkTimeoutError(ActionTimeoutError):
    """
    Exception raised when network operations time out.

    This is a specialized timeout error for network-related operations
    such as API calls, model requests, and service communications.
    """

    def __init__(
        self,
        message: str,
        url: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        error_code: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Initialize network timeout error.

        Args:
            message: Human-readable error message.
            url: The URL that timed out (if applicable).
            timeout_seconds: The timeout period that was exceeded.
            error_code: Optional error code.
            context: Additional context about the network timeout.
        """
        context = context or {}
        if url:
            context["url"] = url

        super().__init__(
            message=message,
            action_type="network_request",
            timeout_seconds=timeout_seconds,
            error_code=error_code,
            context=context,
        )
        self.url = url
