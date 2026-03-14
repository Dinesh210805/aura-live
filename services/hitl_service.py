"""
Human-in-the-Loop (HITL) Service.

Allows agents to pause execution and ask users questions via the app UI.
Supports various interaction types:
- Confirmation (yes/no)
- Single choice (select one from options)
- Multiple choice (select many)
- Text input (free-form response)
- Notification (inform user, wait for acknowledgment)
- Action required (user must do something on device)

Usage:
    hitl = get_hitl_service()
    
    # Ask for confirmation
    response = await hitl.ask_confirmation(
        "Multiple contacts named John found. Do you want to see the list?"
    )
    
    # Show options
    choice = await hitl.ask_choice(
        "Which John do you mean?",
        options=["John Smith (+1234)", "John Doe (+5678)", "Johnny B (+9999)"]
    )
    
    # Wait for user action
    await hitl.wait_for_user_action(
        "Please unlock the app with your fingerprint",
        action_type="biometric_unlock"
    )
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from weakref import WeakSet

from fastapi import WebSocket

from utils.logger import get_logger

logger = get_logger(__name__)


class HITLQuestionType(Enum):
    """Types of HITL interactions."""
    CONFIRMATION = "confirmation"      # Yes/No question
    SINGLE_CHOICE = "single_choice"    # Select one option
    MULTIPLE_CHOICE = "multiple_choice"  # Select multiple options
    TEXT_INPUT = "text_input"          # Free-form text
    NOTIFICATION = "notification"      # Info message, wait for OK
    ACTION_REQUIRED = "action_required"  # User must do something on device


@dataclass
class HITLQuestion:
    """A question to present to the user."""
    id: str
    question_type: HITLQuestionType
    title: str
    message: str
    options: List[str] = field(default_factory=list)
    default_option: Optional[str] = None
    timeout_seconds: float = 60.0
    allow_cancel: bool = True
    action_type: Optional[str] = None  # For ACTION_REQUIRED: "biometric", "permission", etc.
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


@dataclass
class HITLResponse:
    """User's response to a HITL question."""
    question_id: str
    success: bool
    cancelled: bool = False
    timed_out: bool = False
    # Response data depends on question type
    confirmed: Optional[bool] = None      # For CONFIRMATION
    selected_option: Optional[str] = None  # For SINGLE_CHOICE
    selected_options: List[str] = field(default_factory=list)  # For MULTIPLE_CHOICE
    text_input: Optional[str] = None      # For TEXT_INPUT
    acknowledged: bool = False            # For NOTIFICATION
    action_completed: bool = False        # For ACTION_REQUIRED
    response_time: float = 0.0


class HITLService:
    """
    Manages Human-in-the-Loop interactions between agents and users.
    
    Agents can call methods like ask_confirmation(), ask_choice() etc.
    which will:
    1. Send a WebSocket message to the Android app
    2. Display a UI dialog/prompt to the user
    3. Wait for and return the user's response
    """
    
    DEFAULT_TIMEOUT = 60.0  # 60 seconds default timeout
    
    def __init__(self):
        self._websockets: WeakSet[WebSocket] = WeakSet()
        self._pending_questions: Dict[str, asyncio.Future] = {}
        self._question_history: List[HITLQuestion] = []
        self._enabled = True
        
        logger.info("🙋 HITL service initialized")
    
    def register_websocket(self, ws: WebSocket) -> None:
        """Register a WebSocket for HITL communication."""
        self._websockets.add(ws)
        logger.debug(f"HITL WebSocket registered, total: {len(self._websockets)}")
    
    def unregister_websocket(self, ws: WebSocket) -> None:
        """Unregister a WebSocket."""
        self._websockets.discard(ws)
        logger.debug(f"HITL WebSocket unregistered, total: {len(self._websockets)}")
    
    def enable(self):
        """Enable HITL interactions."""
        self._enabled = True
        logger.info("🙋 HITL enabled")
    
    def disable(self):
        """Disable HITL (questions will auto-confirm/use defaults)."""
        self._enabled = False
        logger.warning("⚠️ HITL disabled - questions will auto-resolve")
    
    # =========================================================================
    # Public API for Agents
    # =========================================================================
    
    async def ask_confirmation(
        self,
        message: str,
        title: str = "Confirmation Required",
        timeout: float = DEFAULT_TIMEOUT,
        default: bool = False
    ) -> bool:
        """
        Ask user for yes/no confirmation.
        
        Args:
            message: The question to ask
            title: Dialog title
            timeout: Seconds to wait for response
            default: Default value if timeout/disabled
            
        Returns:
            True if user confirmed, False otherwise
        """
        if not self._enabled:
            logger.info(f"🙋 HITL disabled, auto-returning: {default}")
            return default
        
        question = HITLQuestion(
            id=self._generate_id(),
            question_type=HITLQuestionType.CONFIRMATION,
            title=title,
            message=message,
            options=["Yes", "No"],
            default_option="Yes" if default else "No",
            timeout_seconds=timeout
        )
        
        response = await self._ask_and_wait(question)
        
        if response.timed_out or response.cancelled:
            return default
        return response.confirmed or False
    
    async def ask_choice(
        self,
        message: str,
        options: List[str],
        title: str = "Please Select",
        timeout: float = DEFAULT_TIMEOUT,
        allow_cancel: bool = True
    ) -> Optional[str]:
        """
        Ask user to select one option from a list.
        
        Args:
            message: The question to ask
            options: List of options to choose from
            title: Dialog title
            timeout: Seconds to wait
            allow_cancel: Whether user can cancel
            
        Returns:
            Selected option string, or None if cancelled/timed out
        """
        if not self._enabled or not options:
            return options[0] if options else None
        
        question = HITLQuestion(
            id=self._generate_id(),
            question_type=HITLQuestionType.SINGLE_CHOICE,
            title=title,
            message=message,
            options=options,
            timeout_seconds=timeout,
            allow_cancel=allow_cancel
        )
        
        response = await self._ask_and_wait(question)
        
        if response.timed_out or response.cancelled:
            return None
        return response.selected_option
    
    async def ask_multiple_choice(
        self,
        message: str,
        options: List[str],
        title: str = "Select Options",
        timeout: float = DEFAULT_TIMEOUT,
        min_selections: int = 0,
        max_selections: Optional[int] = None
    ) -> List[str]:
        """
        Ask user to select multiple options.
        
        Returns:
            List of selected options (may be empty)
        """
        if not self._enabled or not options:
            return []
        
        question = HITLQuestion(
            id=self._generate_id(),
            question_type=HITLQuestionType.MULTIPLE_CHOICE,
            title=title,
            message=message,
            options=options,
            timeout_seconds=timeout,
            metadata={"min_selections": min_selections, "max_selections": max_selections}
        )
        
        response = await self._ask_and_wait(question)
        return response.selected_options
    
    async def ask_text_input(
        self,
        message: str,
        title: str = "Input Required",
        placeholder: str = "",
        timeout: float = DEFAULT_TIMEOUT,
        default: str = ""
    ) -> str:
        """
        Ask user for text input.
        
        Returns:
            User's input text, or default if cancelled/timed out
        """
        if not self._enabled:
            return default
        
        question = HITLQuestion(
            id=self._generate_id(),
            question_type=HITLQuestionType.TEXT_INPUT,
            title=title,
            message=message,
            timeout_seconds=timeout,
            metadata={"placeholder": placeholder, "default": default}
        )
        
        response = await self._ask_and_wait(question)
        
        if response.timed_out or response.cancelled:
            return default
        return response.text_input or default
    
    async def notify(
        self,
        message: str,
        title: str = "Notice",
        timeout: float = DEFAULT_TIMEOUT
    ) -> bool:
        """
        Show a notification and wait for user to acknowledge.
        
        Returns:
            True if acknowledged, False if timed out
        """
        if not self._enabled:
            return True
        
        question = HITLQuestion(
            id=self._generate_id(),
            question_type=HITLQuestionType.NOTIFICATION,
            title=title,
            message=message,
            options=["OK"],
            timeout_seconds=timeout,
            allow_cancel=False
        )
        
        response = await self._ask_and_wait(question)
        return response.acknowledged
    
    async def wait_for_user_action(
        self,
        message: str,
        action_type: str,
        title: str = "Action Required",
        timeout: float = 120.0,  # Longer timeout for user actions
        instructions: Optional[str] = None
    ) -> bool:
        """
        Wait for user to complete an action on the device.
        
        Common action_types:
        - "biometric_unlock": Wait for fingerprint/face unlock
        - "permission_grant": Wait for permission dialog
        - "manual_step": Wait for user to do something manually
        - "app_unlock": Wait for app-specific unlock
        
        Args:
            message: What the user needs to do
            action_type: Type of action for app to track
            title: Dialog title
            timeout: Seconds to wait
            instructions: Additional instructions
            
        Returns:
            True if action completed, False if cancelled/timed out
        """
        if not self._enabled:
            logger.warning(f"⚠️ HITL disabled, cannot wait for action: {action_type}")
            return False
        
        question = HITLQuestion(
            id=self._generate_id(),
            question_type=HITLQuestionType.ACTION_REQUIRED,
            title=title,
            message=message,
            action_type=action_type,
            timeout_seconds=timeout,
            metadata={"instructions": instructions} if instructions else {}
        )
        
        response = await self._ask_and_wait(question)
        return response.action_completed
    
    # =========================================================================
    # Internal Methods
    # =========================================================================
    
    def _generate_id(self) -> str:
        """Generate unique question ID."""
        return f"hitl_{uuid.uuid4().hex[:12]}"
    
    async def _ask_and_wait(self, question: HITLQuestion) -> HITLResponse:
        """
        Send question to app and wait for response.
        
        Args:
            question: The question to ask
            
        Returns:
            User's response
        """
        start_time = time.time()
        self._question_history.append(question)
        
        # Create future for response
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending_questions[question.id] = future
        
        # Send to all connected WebSockets
        await self._broadcast_question(question)
        
        logger.info(f"🙋 HITL question sent: [{question.question_type.value}] {question.message[:50]}...")
        
        try:
            # Wait for response with timeout
            response = await asyncio.wait_for(future, timeout=question.timeout_seconds)
            response.response_time = time.time() - start_time
            logger.info(f"✅ HITL response received in {response.response_time:.1f}s")
            return response
            
        except asyncio.TimeoutError:
            logger.warning(f"⏰ HITL question timed out after {question.timeout_seconds}s: {question.id}")
            return HITLResponse(
                question_id=question.id,
                success=False,
                timed_out=True,
                response_time=time.time() - start_time
            )
        finally:
            # Cleanup
            self._pending_questions.pop(question.id, None)
    
    async def _broadcast_question(self, question: HITLQuestion):
        """Broadcast question to all connected WebSockets."""
        message = {
            "type": "hitl_question",
            "question_id": question.id,
            "question_type": question.question_type.value,
            "title": question.title,
            "message": question.message,
            "options": question.options,
            "default_option": question.default_option,
            "timeout_seconds": question.timeout_seconds,
            "allow_cancel": question.allow_cancel,
            "action_type": question.action_type,
            "metadata": question.metadata,
            "timestamp": int(time.time() * 1000)
        }
        
        dead_sockets = []
        for ws in self._websockets:
            try:
                await ws.send_json(message)
            except Exception as e:
                logger.debug(f"Failed to send HITL question: {e}")
                dead_sockets.append(ws)
        
        # Cleanup dead sockets
        for ws in dead_sockets:
            self._websockets.discard(ws)
    
    def handle_response(self, response_data: Dict[str, Any]) -> bool:
        """
        Handle HITL response from Android app.
        
        Called by WebSocket router when hitl_response message received.
        
        Args:
            response_data: Response payload from app
            
        Returns:
            True if response was handled, False if question not found
        """
        question_id = response_data.get("question_id")
        if not question_id:
            logger.warning("HITL response missing question_id")
            return False
        
        future = self._pending_questions.get(question_id)
        if not future:
            logger.warning(f"HITL response for unknown question: {question_id}")
            return False
        
        # Build response object
        response = HITLResponse(
            question_id=question_id,
            success=response_data.get("success", True),
            cancelled=response_data.get("cancelled", False),
            confirmed=response_data.get("confirmed"),
            selected_option=response_data.get("selected_option"),
            selected_options=response_data.get("selected_options", []),
            text_input=response_data.get("text_input"),
            acknowledged=response_data.get("acknowledged", False),
            action_completed=response_data.get("action_completed", False)
        )
        
        # Resolve the future
        if not future.done():
            future.set_result(response)
            logger.info(f"✅ HITL response handled: {question_id}")
            return True
        
        return False
    
    def get_pending_questions(self) -> List[Dict[str, Any]]:
        """Get list of currently pending questions."""
        return [
            {
                "id": q.id,
                "type": q.question_type.value,
                "message": q.message,
                "created_at": q.created_at,
                "age_seconds": time.time() - q.created_at
            }
            for q in self._question_history
            if q.id in self._pending_questions
        ]
    
    def cancel_question(self, question_id: str) -> bool:
        """Cancel a pending question (e.g., if task is aborted)."""
        future = self._pending_questions.get(question_id)
        if future and not future.done():
            response = HITLResponse(
                question_id=question_id,
                success=False,
                cancelled=True
            )
            future.set_result(response)
            logger.info(f"🚫 HITL question cancelled: {question_id}")
            return True
        return False
    
    def cancel_all_pending(self):
        """Cancel all pending questions."""
        for question_id in list(self._pending_questions.keys()):
            self.cancel_question(question_id)


# Singleton instance
_hitl_service: Optional[HITLService] = None


def get_hitl_service() -> HITLService:
    """Get the global HITL service instance."""
    global _hitl_service
    if _hitl_service is None:
        _hitl_service = HITLService()
    return _hitl_service
