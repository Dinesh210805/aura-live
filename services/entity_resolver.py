"""
Entity Resolver for AURA conversational AI.

Resolves pronouns and references like 'it', 'that', 'there', 'again'
to actual entities from conversation context.
"""

import re
import time
from typing import Optional

from utils.logger import get_logger
from utils.types import FullConversationContext

logger = get_logger(__name__)


class EntityResolver:
    """
    Resolves pronouns and vague references to concrete entities.
    
    Patterns handled:
    - "it" → last mentioned entity
    - "that" → last target
    - "there" → current app/location
    - "again" → repeat last action
    - "the same" → last entity of same type
    - "him/her" → last contact
    """

    # Patterns that need resolution (word boundaries for accuracy)
    PRONOUN_PATTERNS = {
        r"\bit\b": "last_entity",
        r"\bthat\b": "last_target",
        r"\bthere\b": "current_app",
        r"\bagain\b": "repeat_action",
        r"\bthe same\b": "last_entity",
        r"\bhim\b": "last_contact",
        r"\bher\b": "last_contact",
    }

    # Device feature keywords for "it" resolution after toggle actions
    DEVICE_FEATURES = {
        "wifi": ["wifi", "wi-fi", "internet", "network"],
        "bluetooth": ["bluetooth", "bt"],
        "torch": ["torch", "flashlight", "flash", "light"],
        "volume": ["volume", "sound"],
        "brightness": ["brightness", "screen brightness"],
    }

    def __init__(self):
        logger.info("✅ EntityResolver initialized")

    def needs_resolution(self, transcript: str) -> bool:
        """Check if the transcript contains pronouns that need resolution."""
        transcript_lower = transcript.lower()
        for pattern in self.PRONOUN_PATTERNS.keys():
            if re.search(pattern, transcript_lower):
                return True
        return False

    def resolve(self, transcript: str, context: FullConversationContext) -> str:
        """
        Replace pronouns with resolved entity values.
        
        Args:
            transcript: Original user transcript with pronouns.
            context: Full conversation context with entity stack.
            
        Returns:
            Modified transcript with pronouns replaced by actual entities.
        """
        if not context:
            logger.warning("No context provided for entity resolution")
            return transcript

        resolved = transcript
        resolutions_made = []

        for pattern, resolution_type in self.PRONOUN_PATTERNS.items():
            if not re.search(pattern, resolved, re.IGNORECASE):
                continue

            # Skip "it" if it's part of a proper name or in all caps (likely an abbreviation)
            if pattern == r"\bit\b":
                # Check if "it" or "IT" appears after a capitalized word (likely a name)
                if re.search(r'\b[A-Z][a-z]+\s+IT\b', resolved):
                    logger.debug("Skipping 'IT' - appears to be part of a name")
                    continue
                # Check if it's all caps (abbreviation like "IT department")
                if re.search(r'\bIT\b', resolved):
                    logger.debug("Skipping 'IT' - appears to be an abbreviation")
                    continue
            
            # Skip "that" if it's part of message content (e.g., "saying that", "telling that")
            if pattern == r"\bthat\b":
                # Check if "that" appears after message-introducing words
                if re.search(r'\b(saying|telling|message|text|write|send|reply)\s+that\b', resolved, re.IGNORECASE):
                    logger.debug("Skipping 'that' - appears to be part of message content")
                    continue

            replacement = self._get_replacement(resolution_type, context)
            if replacement:
                # Replace the pronoun with the resolved entity
                resolved = re.sub(pattern, replacement, resolved, flags=re.IGNORECASE)
                resolutions_made.append(f"{pattern} → {replacement}")

        if resolutions_made:
            logger.info(f"🔗 Entity resolution: {resolutions_made}")
            logger.info(f"   Original: '{transcript}'")
            logger.info(f"   Resolved: '{resolved}'")

        return resolved

    def _get_replacement(
        self, resolution_type: str, context: FullConversationContext
    ) -> Optional[str]:
        """Get the replacement value based on resolution type."""

        if resolution_type == "last_entity":
            # For "it" after device toggles, resolve to the device feature
            if context.last_action and any(
                x in context.last_action.lower()
                for x in ["wifi", "bluetooth", "torch", "flashlight", "volume"]
            ):
                return self._extract_feature_from_action(context.last_action)
            
            # Otherwise, use last entity from stack
            entity = context.get_last_entity()
            return entity.value if entity else None

        elif resolution_type == "last_target":
            return context.last_target

        elif resolution_type == "current_app":
            return context.current_app

        elif resolution_type == "repeat_action":
            # For "again", we don't replace the word, the intent parser handles repeat
            return None

        elif resolution_type == "last_contact":
            entity = context.get_last_entity("contact")
            return entity.value if entity else None

        return None

    def _extract_feature_from_action(self, action: str) -> Optional[str]:
        """Extract the device feature name from an action string."""
        action_lower = action.lower()
        
        for feature, keywords in self.DEVICE_FEATURES.items():
            for keyword in keywords:
                if keyword in action_lower:
                    return feature
        
        return None

    def get_resolution_context(
        self, transcript: str, context: FullConversationContext
    ) -> dict:
        """
        Get detailed resolution info for debugging/logging.
        
        Returns dict with what would be resolved and why.
        """
        result = {
            "original": transcript,
            "needs_resolution": self.needs_resolution(transcript),
            "resolutions": [],
            "context_snapshot": {
                "current_app": context.current_app if context else None,
                "last_action": context.last_action if context else None,
                "last_target": context.last_target if context else None,
                "entity_count": len(context.entity_stack) if context else 0,
            },
        }

        if not context:
            return result

        for pattern, resolution_type in self.PRONOUN_PATTERNS.items():
            if re.search(pattern, transcript, re.IGNORECASE):
                replacement = self._get_replacement(resolution_type, context)
                result["resolutions"].append({
                    "pattern": pattern,
                    "type": resolution_type,
                    "resolved_to": replacement,
                })

        return result


# Singleton instance
_entity_resolver: Optional[EntityResolver] = None


def get_entity_resolver() -> EntityResolver:
    """Get the global entity resolver instance."""
    global _entity_resolver
    if _entity_resolver is None:
        _entity_resolver = EntityResolver()
    return _entity_resolver
