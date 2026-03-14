"""Simple conversation context manager for multi-turn dialogue with error tracking."""

from collections import deque
from datetime import datetime
from typing import Dict, List, Optional


class ConversationManager:
    """Manages conversation history for context retention with error awareness."""

    def __init__(self, max_turns: int = 5):
        self._sessions: Dict[str, deque] = {}
        self._max_turns = max_turns
        self._error_counts: Dict[str, int] = {}  # Track errors per session

    def add_turn(
        self,
        session_id: str,
        user_message: str,
        assistant_message: str,
        success: bool = True,
        error: Optional[str] = None,
    ):
        """Add a conversation turn with success tracking."""
        if session_id not in self._sessions:
            self._sessions[session_id] = deque(maxlen=self._max_turns)
            self._error_counts[session_id] = 0

        turn_data = {
            "user": user_message,
            "assistant": assistant_message,
            "timestamp": datetime.utcnow().isoformat(),
            "success": success,
        }

        if error:
            turn_data["error"] = error
            self._error_counts[session_id] += 1

        self._sessions[session_id].append(turn_data)

    def get_history(self, session_id: str) -> List[Dict]:
        """Get conversation history for a session."""
        if session_id not in self._sessions:
            return []
        return list(self._sessions[session_id])

    def get_error_count(self, session_id: str) -> int:
        """Get number of errors in this session."""
        return self._error_counts.get(session_id, 0)

    def has_recent_errors(self, session_id: str, threshold: int = 2) -> bool:
        """Check if session has recent repeated errors."""
        return self.get_error_count(session_id) >= threshold

    def clear_session(self, session_id: str):
        """Clear session history."""
        if session_id in self._sessions:
            del self._sessions[session_id]
        if session_id in self._error_counts:
            del self._error_counts[session_id]

    def format_history(self, session_id: str, include_errors: bool = False) -> str:
        """Format history for LLM context."""
        history = self.get_history(session_id)
        if not history:
            return ""

        formatted = []
        for turn in history:
            formatted.append(f"User: {turn['user']}")
            formatted.append(f"Assistant: {turn['assistant']}")
            if include_errors and not turn.get("success", True):
                formatted.append(f"  [Error: {turn.get('error', 'Unknown')}]")

        return "\n".join(formatted)
