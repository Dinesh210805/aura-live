"""
Conversation Session Manager for AURA.

Tracks conversation context across multiple turns including:
- Entity tracking for pronoun resolution
- Device state for toggle commands
- Response history for variation
- Full context export for AI responses
"""

import time
from typing import Dict, List, Optional

from utils.logger import get_logger
from utils.types import DeviceState, EntityReference, FullConversationContext

logger = get_logger(__name__)

# Session timeout: 5 minutes of inactivity resets session
SESSION_TIMEOUT = 300  # seconds
MAX_ENTITY_STACK = 10  # Keep last 10 entities
MAX_RESPONSE_HISTORY = 5  # Keep last 5 responses


class ConversationSession:
    """Manages conversation state for a single user session with full context."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.conversation_turn = 0
        self.has_introduced = False
        self.last_interaction_time = time.time()
        self.created_at = time.time()

        # Entity tracking for pronoun resolution
        self.current_app: Optional[str] = None
        self.last_action: Optional[str] = None
        self.last_target: Optional[str] = None
        self.entity_stack: List[Dict] = []  # Stack of {type, value, timestamp}

        # Device state tracking for "turn it off" resolution
        self.device_states: Dict[str, bool] = {}

        # Response history for natural variation
        self.response_history: List[str] = []

        # Emotional context detection
        self.emotional_context: Optional[str] = None

    def update(self):
        """Update session on new interaction."""
        current_time = time.time()
        time_since_last = current_time - self.last_interaction_time

        # Check if session timed out (5 min inactivity)
        if time_since_last > SESSION_TIMEOUT:
            logger.info(
                f"Session {self.session_id} timed out after {time_since_last:.0f}s inactivity - resetting"
            )
            self._reset_session()
        else:
            self.conversation_turn += 1

        self.last_interaction_time = current_time

    def _reset_session(self):
        """Reset session state on timeout."""
        self.conversation_turn = 0
        self.has_introduced = False
        self.current_app = None
        self.last_action = None
        self.last_target = None
        self.entity_stack = []
        self.device_states = {}
        self.response_history = []
        self.emotional_context = None

    def is_follow_up(self) -> bool:
        """Check if this is a follow-up (within 60 seconds of last interaction)."""
        time_since_last = time.time() - self.last_interaction_time
        return time_since_last < 60

    def mark_introduced(self):
        """Mark that AURA has introduced itself."""
        self.has_introduced = True
        logger.info(
            f"Session {self.session_id}: AURA introduced (turn {self.conversation_turn})"
        )

    def push_entity(self, entity_type: str, value: str):
        """
        Track a mentioned entity for later resolution.
        
        Args:
            entity_type: Type of entity ('app', 'contact', 'action', 'feature')
            value: The actual entity value
        """
        if not value:
            return

        entity = {
            "entity_type": entity_type,
            "value": value,
            "timestamp": time.time(),
        }
        self.entity_stack.append(entity)

        # Keep stack bounded
        if len(self.entity_stack) > MAX_ENTITY_STACK:
            self.entity_stack = self.entity_stack[-MAX_ENTITY_STACK:]

        # Update convenience fields
        if entity_type == "app":
            self.current_app = value
        self.last_target = value

        logger.debug(f"Entity pushed: {entity_type}={value} (stack size: {len(self.entity_stack)})")

    def get_last_entity(self, entity_type: Optional[str] = None) -> Optional[Dict]:
        """
        Get the most recent entity, optionally filtered by type.
        
        Args:
            entity_type: Optional filter by entity type
            
        Returns:
            Entity dict or None
        """
        if not self.entity_stack:
            return None

        if entity_type is None:
            return self.entity_stack[-1]

        for entity in reversed(self.entity_stack):
            if entity.get("entity_type") == entity_type:
                return entity

        return None

    def update_device_state(self, feature: str, state: bool):
        """
        Update a device feature state.
        
        Args:
            feature: Feature name ('wifi', 'bluetooth', 'torch')
            state: True for on, False for off
        """
        self.device_states[feature] = state
        self.last_action = f"{feature}_{'on' if state else 'off'}"
        
        # Also track as entity for "turn it off" resolution
        self.push_entity("feature", feature)
        
        logger.debug(f"Device state updated: {feature}={state}")

    def add_response(self, response: str):
        """
        Add a response to history for variation tracking.
        
        Args:
            response: The response text that was generated
        """
        if not response:
            return

        self.response_history.append(response)

        # Keep history bounded
        if len(self.response_history) > MAX_RESPONSE_HISTORY:
            self.response_history = self.response_history[-MAX_RESPONSE_HISTORY:]

    def set_emotional_context(self, emotion: Optional[str]):
        """Set detected emotional context."""
        self.emotional_context = emotion
        if emotion:
            logger.debug(f"Emotional context set: {emotion}")

    def get_context(self) -> Dict:
        """Get basic conversation context (backward compatible)."""
        return {
            "conversation_turn": self.conversation_turn,
            "has_introduced": self.has_introduced,
            "is_follow_up": self.is_follow_up(),
            "session_id": self.session_id,
            "last_interaction_time": self.last_interaction_time,
        }

    def get_full_context(self) -> FullConversationContext:
        """
        Get full conversation context for AI response generation.
        
        Returns:
            FullConversationContext with all tracked state
        """
        # Convert entity stack to EntityReference objects
        entity_refs = [
            EntityReference(
                entity_type=e.get("entity_type", "unknown"),
                value=e.get("value", ""),
                timestamp=e.get("timestamp", time.time()),
            )
            for e in self.entity_stack
        ]

        # Convert device states to DeviceState object
        device_state = DeviceState(
            wifi=self.device_states.get("wifi"),
            bluetooth=self.device_states.get("bluetooth"),
            torch=self.device_states.get("torch"),
        )

        return FullConversationContext(
            current_app=self.current_app,
            last_action=self.last_action,
            last_target=self.last_target,
            entity_stack=entity_refs,
            device_states=device_state,
            response_history=list(self.response_history),
            emotional_context=self.emotional_context,
            conversation_turn=self.conversation_turn,
            has_introduced=self.has_introduced,
            session_id=self.session_id,
        )


class ConversationSessionManager:
    """Global session manager (singleton)."""

    def __init__(self):
        self.sessions: Dict[str, ConversationSession] = {}
        self._cleanup_interval = 600  # Cleanup every 10 minutes
        self._last_cleanup = time.time()

    def get_session(self, session_id: str) -> ConversationSession:
        """Get or create a session."""
        # Periodic cleanup of old sessions
        if time.time() - self._last_cleanup > self._cleanup_interval:
            self._cleanup_old_sessions()

        if session_id not in self.sessions:
            logger.info(f"Creating new conversation session: {session_id}")
            self.sessions[session_id] = ConversationSession(session_id)

        return self.sessions[session_id]

    def _cleanup_old_sessions(self):
        """Remove sessions inactive for > 1 hour."""
        current_time = time.time()
        expired_sessions = [
            sid
            for sid, session in self.sessions.items()
            if current_time - session.last_interaction_time > 3600
        ]

        for sid in expired_sessions:
            logger.info(f"Cleaning up expired session: {sid}")
            del self.sessions[sid]

        self._last_cleanup = current_time
        logger.info(
            f"Session cleanup: removed {len(expired_sessions)}, active: {len(self.sessions)}"
        )


# Global instance
_session_manager: Optional[ConversationSessionManager] = None


def get_session_manager() -> ConversationSessionManager:
    """Get the global session manager."""
    global _session_manager
    if _session_manager is None:
        _session_manager = ConversationSessionManager()
    return _session_manager

