"""
Intent Normalization Service

Maps semantic intent actions to canonical executable actions.
Uses ACTION_REGISTRY as the single source of truth for valid actions.
Unknown actions gracefully fallback to general_interaction.
"""

import re
from typing import Any

from config.action_types import ACTION_REGISTRY
from utils.logger import get_logger

logger = get_logger(__name__)

# Prefixes that map to open_app (extract app name after prefix)
_APP_OPEN_PREFIXES = {"open", "launch", "start", "access", "use", "goto", "go_to", "go"}

# Actions that map to read_screen
_SCREEN_READ_ACTIONS = {"describe", "analyze", "what", "see", "view", "read"}


def normalize_intent_action(intent: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize semantic intent actions to executable actions.
    
    Flow:
    1. If action is in ACTION_REGISTRY → pass through
    2. Try semantic patterns (open_*, describe_*, etc.)
    3. Unknown actions → general_interaction with original action as goal
    
    Never fails - always returns a valid intent.
    """
    action = intent.get("action", "").lower().strip()
    if not action:
        return _fallback_intent(intent, "empty_action")

    # Already a valid action in registry
    if action in ACTION_REGISTRY:
        return intent

    # Try app-opening patterns: "open_settings", "launch-instagram", etc.
    normalized = _try_app_open_normalization(action, intent)
    if normalized:
        logger.info(f"Normalized: '{action}' → 'open_app' (recipient='{normalized.get('recipient', 'N/A')}')")
        return normalized

    # Try screen-reading patterns: "describe", "analyze_screen", etc.
    if _is_screen_read_action(action):
        result = intent.copy()
        result["action"] = "read_screen"
        logger.info(f"Normalized: '{action}' → 'read_screen'")
        return result

    # Unknown action → graceful fallback to general_interaction
    # Preserve the original action as a goal for intelligent handling
    return _fallback_intent(intent, action)


def _fallback_intent(intent: dict[str, Any], original_action: str) -> dict[str, Any]:
    """
    Convert unknown action to general_interaction.
    Preserves original intent in parameters for intelligent downstream handling.
    """
    result = intent.copy()
    result["action"] = "general_interaction"
    
    # Store original action as goal for downstream agents to reason about
    params = result.get("parameters", {})
    params["original_action"] = original_action
    params["goal"] = intent.get("content") or original_action
    result["parameters"] = params
    
    logger.info(f"Unknown action '{original_action}' → general_interaction (goal preserved)")
    return result


def _try_app_open_normalization(action: str, intent: dict[str, Any]) -> dict[str, Any] | None:
    """Extract app name from 'open_settings', 'launch-instagram' patterns."""
    parts = re.split(r"[_\-\s]+", action, maxsplit=1)
    if len(parts) != 2:
        return None
    
    prefix, app_name = parts
    if prefix not in _APP_OPEN_PREFIXES:
        return None
    
    result = intent.copy()
    result["action"] = "open_app"
    
    if not result.get("recipient") and app_name:
        result["recipient"] = app_name.replace("_", " ").replace("-", " ").title()
    
    return result


def _is_screen_read_action(action: str) -> bool:
    """Check if action is a screen-reading variant."""
    base = re.split(r"[_\-\s]+", action)[0]
    return base in _SCREEN_READ_ACTIONS


def is_valid_action(action: str) -> bool:
    """Check if action is in the registry."""
    return action.lower().strip() in ACTION_REGISTRY


def list_valid_actions() -> list:
    """Return sorted list of all valid actions."""
    return sorted(ACTION_REGISTRY.keys())
