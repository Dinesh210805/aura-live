"""Custom exceptions for AURA agent pipeline."""


class AuraAgentError(Exception):
    """Base exception for all AURA agent errors."""
    pass


class TargetNotFoundError(AuraAgentError):
    """Raised when a UI target element cannot be found after perception.

    # FIXED: FIX-007 — created to route coordinator failures through
    # LangGraph retry system instead of coordinator's internal retry loop.
    """
    def __init__(self, message: str, target: str = "", action_type: str = ""):
        super().__init__(message)
        self.target = target
        self.action_type = action_type


class PerceptionFailureError(AuraAgentError):
    """Raised when perception cannot be obtained after all fallback attempts.

    # FIXED: FIX-008 — created to surface VISION mode screenshot failures
    # to the retry system instead of silently falling back to UI_TREE.
    """
    def __init__(self, message: str, modality=None):
        super().__init__(message)
        self.modality = modality


class AuraTimeoutError(AuraAgentError):
    """Raised when graph execution exceeds the configured timeout.

    # FIXED: FIX-015 — created for graph-level timeout handling.
    """
    pass
