"""
Validator Agent for the AURA backend.

Rule-based validation for intents before execution.
Fast Python validation with zero LLM calls.
"""

from typing import Any, Dict, List, Optional

from config.action_types import DANGEROUS_ACTIONS, REQUIRED_FIELDS, VALID_ACTIONS
from utils.logger import get_logger
from utils.types import IntentObject

logger = get_logger(__name__)


class ValidationResult:
    """Result of intent validation."""

    def __init__(
        self,
        is_valid: bool,
        confidence: float = 1.0,
        issues: Optional[List[str]] = None,
        suggestions: Optional[List[str]] = None,
        requires_confirmation: bool = False,
        refined_intent: Optional[Dict[str, Any]] = None,
    ):
        self.is_valid = is_valid
        self.confidence = confidence
        self.issues = issues or []
        self.suggestions = suggestions or []
        self.requires_confirmation = requires_confirmation
        self.refined_intent = refined_intent

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "confidence": self.confidence,
            "issues": self.issues,
            "suggestions": self.suggestions,
            "requires_confirmation": self.requires_confirmation,
            "has_refinements": self.refined_intent is not None,
        }


class ValidatorAgent:
    """
    Validator Agent - Rule-based intent validation.

    Fast Python validation with zero LLM calls.
    Checks for required fields, dangerous actions, and low confidence.
    """

    def __init__(self):
        """Initialize the Validator agent."""
        logger.info("✅ Validator agent initialized (rule-based mode)")

    def validate_intent(
        self,
        intent: IntentObject,
    ) -> ValidationResult:
        """
        Validate intent using rule-based Python checks (no LLM).
        Fast validation with zero API calls.

        Args:
            intent: The intent to validate.

        Returns:
            ValidationResult with status and any issues found.
        """
        issues = []
        suggestions = []

        # 1. Check if action exists
        if not intent.action or intent.action.strip() == "":
            issues.append("Action is missing or empty")
            return ValidationResult(
                is_valid=False,
                issues=issues,
                suggestions=["Command could not be understood. Please try again."],
            )

        # 2. Normalize action for comparison
        action_lower = intent.action.lower().replace("-", "_").replace(" ", "_")

        # 3. Check if action is valid
        valid_actions_lower = [a.lower() for a in VALID_ACTIONS]
        if action_lower not in valid_actions_lower:
            # Check common variations
            action_map = {
                "open": "open_app",
                "launch": "open_app",
                "start": "open_app",
                "message": "send_message",
                "text": "send_message",
                "call": "make_call",
            }
            if action_lower not in action_map:
                issues.append(f"Unknown action: {intent.action}")
                suggestions.append(
                    f"Did you mean one of: {', '.join(VALID_ACTIONS[:5])}?"
                )

        # 4. Check required fields for specific actions
        if action_lower in REQUIRED_FIELDS:
            required = REQUIRED_FIELDS[action_lower]
            for field in required:
                value = getattr(intent, field, None)
                if not value or (isinstance(value, str) and value.strip() == ""):
                    issues.append(f"{intent.action} requires {field}")
                    suggestions.append(
                        f"Please specify who or what for {intent.action}"
                    )

        # 5. Check dangerous actions
        if action_lower in [a.lower() for a in DANGEROUS_ACTIONS]:
            suggestions.append(f"⚠️ {intent.action} is a potentially dangerous action")

        # 6. Check confidence
        if intent.confidence < 0.5:
            issues.append(f"Low confidence: {intent.confidence:.2f}")
            suggestions.append("Command may not have been understood clearly")

        # 7. Determine validity
        is_valid = len(issues) == 0 or (
            len(issues) == 1
            and "Low confidence" in issues[0]
            and intent.confidence >= 0.3
        )

        if is_valid:
            logger.info(f"✅ Validation passed: {intent.action}")
        else:
            logger.warning(f"⚠️ Validation failed: {issues}")

        return ValidationResult(
            is_valid=is_valid,
            issues=issues,
            suggestions=suggestions,
        )
