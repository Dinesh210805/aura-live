"""
Sensitive action detection and blocking policy.

Prevents execution of dangerous operations like banking, system shutdown, file deletion.
"""

from typing import Dict, List, Optional
from utils.logger import get_logger

logger = get_logger(__name__)


class SensitiveActionPolicy:
    """Policy to detect and block sensitive/dangerous operations."""

    # Sensitive action categories
    BANKING_KEYWORDS = [
        "bank", "banking", "payment", "wallet", "paypal", "venmo", "cash app",
        "gpay", "google pay", "apple pay", "paytm", "phonepe", "transfer money",
        "send money", "credit card", "debit card", "upi", "net banking"
    ]

    SYSTEM_SHUTDOWN_KEYWORDS = [
        "shutdown", "power off", "restart", "reboot", "factory reset",
        "reset phone", "wipe data", "format", "hard reset",
        "switch off", "turn off device", "turn off phone", "turn off my phone",
        "turn off my device", "power down", "shut down phone", "shut down device"
    ]

    DESTRUCTIVE_KEYWORDS = [
        "delete", "remove", "uninstall", "clear data", "clear cache",
        "erase", "wipe", "permanently delete", "destroy",
        "reset phone", "reset device", "reset my phone", "factory data reset",
        "erase all data", "wipe phone", "wipe device"
    ]

    SECURITY_KEYWORDS = [
        "disable security", "turn off password", "remove lock",
        "disable pin", "turn off fingerprint", "disable face unlock",
        "remove pattern", "unlock bootloader"
    ]

    PERMISSION_KEYWORDS = [
        "grant all permissions", "disable permission", "turn off security",
        "allow unknown sources", "enable developer mode"
    ]

    SENSITIVE_APPS = [
        "bank of america", "chase", "wells fargo", "paypal", "venmo",
        "google pay", "samsung pay", "apple wallet", "robinhood",
        "coinbase", "crypto.com", "binance", "paytm", "phonepe",
        "bhim", "axis bank", "hdfc bank", "icici bank", "sbi",
        "password manager", "lastpass", "1password", "bitwarden"
    ]

    def __init__(self):
        """Initialize the sensitive action policy."""
        self.enabled = True
        self.blocked_count = 0

    def is_sensitive(self, command: str, intent: Optional[str] = None) -> tuple[bool, Optional[str]]:
        """
        Check if a command contains sensitive actions.

        Args:
            command: The user command text
            intent: Optional intent classification

        Returns:
            Tuple of (is_sensitive: bool, reason: str or None)
        """
        if not self.enabled:
            return False, None

        command_lower = command.lower()

        # Check banking operations
        if self._contains_keywords(command_lower, self.BANKING_KEYWORDS):
            return True, "banking_operation"

        # Check system shutdown/reset
        if self._contains_keywords(command_lower, self.SYSTEM_SHUTDOWN_KEYWORDS):
            return True, "system_shutdown"

        # Check destructive operations
        if self._contains_keywords(command_lower, self.DESTRUCTIVE_KEYWORDS):
            return True, "destructive_operation"

        # Check security modifications
        if self._contains_keywords(command_lower, self.SECURITY_KEYWORDS):
            return True, "security_modification"

        # Check permission changes
        if self._contains_keywords(command_lower, self.PERMISSION_KEYWORDS):
            return True, "permission_change"

        # Check sensitive app launch
        if self._contains_keywords(command_lower, self.SENSITIVE_APPS):
            if any(word in command_lower for word in ["open", "launch", "start"]):
                return True, "sensitive_app_access"

        return False, None

    def _contains_keywords(self, text: str, keywords: List[str]) -> bool:
        """Check if text contains any of the keywords."""
        return any(keyword in text for keyword in keywords)

    def get_blocked_response(self, reason: str, command: str) -> Dict:
        """
        Get the response for a blocked command.

        Args:
            reason: The reason the command was blocked
            command: The original command

        Returns:
            Response dictionary with error details
        """
        self.blocked_count += 1
        logger.warning(f"🚫 Blocked sensitive command: {command} (reason: {reason})")

        reason_messages = {
            "banking_operation": (
                "I cannot access banking or financial apps for your security. "
                "Please handle financial transactions manually on your device."
            ),
            "system_shutdown": (
                "I cannot perform system shutdown or reset operations for safety reasons. "
                "Please use your device's power button or settings to perform these actions."
            ),
            "destructive_operation": (
                "I cannot perform destructive operations like deleting files or uninstalling apps. "
                "Please do this manually to prevent accidental data loss."
            ),
            "security_modification": (
                "I cannot modify security settings for your protection. "
                "Please change security settings manually in your device settings."
            ),
            "permission_change": (
                "I cannot change app permissions or security settings. "
                "Please modify permissions manually in settings for security reasons."
            ),
            "sensitive_app_access": (
                "I cannot open banking or password management apps for your security. "
                "Please open these apps manually."
            ),
        }

        message = reason_messages.get(reason, "This action is not supported for security reasons.")

        return {
            "status": "blocked",
            "error_code": "SENSITIVE_ACTION_BLOCKED",
            "reason": reason,
            "message": message,
            "spoken_response": message,
            "command": command,
            "blocked_count": self.blocked_count,
        }

    def add_custom_keyword(self, category: str, keyword: str) -> bool:
        """
        Add a custom sensitive keyword to a category.

        Args:
            category: Category name (banking, shutdown, destructive, security, permission)
            keyword: Keyword to add

        Returns:
            Success status
        """
        category_map = {
            "banking": self.BANKING_KEYWORDS,
            "shutdown": self.SYSTEM_SHUTDOWN_KEYWORDS,
            "destructive": self.DESTRUCTIVE_KEYWORDS,
            "security": self.SECURITY_KEYWORDS,
            "permission": self.PERMISSION_KEYWORDS,
            "apps": self.SENSITIVE_APPS,
        }

        if category in category_map:
            if keyword.lower() not in category_map[category]:
                category_map[category].append(keyword.lower())
                logger.info(f"Added custom sensitive keyword: {keyword} to {category}")
                return True
        return False

    def get_stats(self) -> Dict:
        """Get statistics about blocked commands."""
        return {
            "enabled": self.enabled,
            "blocked_count": self.blocked_count,
            "categories": {
                "banking": len(self.BANKING_KEYWORDS),
                "shutdown": len(self.SYSTEM_SHUTDOWN_KEYWORDS),
                "destructive": len(self.DESTRUCTIVE_KEYWORDS),
                "security": len(self.SECURITY_KEYWORDS),
                "permission": len(self.PERMISSION_KEYWORDS),
                "sensitive_apps": len(self.SENSITIVE_APPS),
            },
        }


# Global singleton instance
sensitive_action_policy = SensitiveActionPolicy()
