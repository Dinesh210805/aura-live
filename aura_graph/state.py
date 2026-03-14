"""
LangGraph state definition for the AURA backend.

This module defines the central TaskState TypedDict that represents
the complete state of a user command as it flows through the graph.
"""

from typing import Any, Dict, List, Optional, TypedDict

from typing_extensions import Annotated

from utils.types import ActionResult, UIElement


# Custom reducer for error messages to handle multiple error sources
def add_errors(existing: Optional[str], new: str) -> str:
    """Add error messages together, joining with semicolon if multiple."""
    if not existing:
        return new
    return f"{existing}; {new}"


# Custom reducer for status - last writer wins
def update_status(existing: Optional[str], new: str) -> str:
    """Update status with the latest value (last writer wins)."""
    return new


# Custom reducer for current_step - take maximum value
def update_step(existing: Optional[int], new: int) -> int:
    """Update current step with maximum value to handle concurrent updates."""
    if existing is None:
        return new
    return max(existing, new)


class TaskState(TypedDict):
    """
    Represents the full state of a single user command.

    This state object is passed between nodes in the LangGraph and accumulates
    information as the task progresses through different processing stages.
    Each key represents a different aspect of the task execution.
    """

    # Audio and text processing
    raw_audio: Optional[bytes]
    """Initial audio data from the user's voice command."""

    transcript: Optional[str]
    """Transcribed text from the speech-to-text service."""

    streaming_transcript: Optional[str]
    """Real-time transcript from WebSocket streaming (takes priority over batch transcript)."""

    language: Optional[str]
    """Preferred spoken language code for STT operations (e.g., 'en', 'es')."""

    intent: Optional[Dict[str, Any]]
    """Structured intent object parsed from the transcript by the Commander agent."""

    # Note: Deprecated - replaced by Perception Controller (see UI Perception Blueprint)
    # Legacy perception state fields - these should not be populated by graph nodes.
    # Perception data must come from Perception Controller via PerceptionBundle.
    # These fields are kept for backward compatibility but should not be used.
    ui_screenshot: Optional[bytes]
    """DEPRECATED: Screenshot data - must come from Perception Controller, not graph nodes."""

    ui_tree: Optional[Dict[str, Any]]
    """DEPRECATED: UI tree data - must come from Perception Controller, not graph nodes."""

    ui_elements: Optional[List[UIElement]]
    """DEPRECATED: UI elements - must come from Perception Controller, not graph nodes."""

    # Planning and execution
    plan: Optional[List[Dict[str, Any]]]
    """Step-by-step execution plan created by the Navigator agent."""

    current_step: Annotated[Optional[int], update_step]
    """Index of the current step being executed (0-based). Uses max reducer to handle concurrent updates."""

    executed_steps: Optional[List[ActionResult]]
    """Log of actions that have been completed with their results."""

    # Feedback and error handling
    feedback_message: Annotated[Optional[str], update_status]
    """Message to be spoken to the user as feedback. Uses last-writer-wins reducer."""

    error_message: Annotated[Optional[str], add_errors]
    """Details of any error that occurred during execution. Uses custom reducer to handle multiple errors."""

    retry_count: Optional[int]
    """Number of times the current step has been retried."""

    max_retries: Optional[int]
    """Maximum number of retries allowed for any step."""

    # Status and metadata
    session_id: Optional[str]
    """Unique session ID for workflow tracking, visualization, and conversation context."""
    
    status: Annotated[Optional[str], update_status]
    """Current status of the task (e.g., 'processing', 'executing', 'completed', 'failed'). Uses last-writer-wins reducer."""

    start_time: Optional[float]
    """Timestamp when the task started processing."""

    end_time: Annotated[Optional[float], update_status]
    """Timestamp when the task completed or failed."""

    task_id: Optional[str]
    """Unique identifier for this task instance."""

    # Workflow tracking
    workflow_steps: Optional[List[Dict[str, Any]]]
    """List of workflow steps for debugging and progress tracking."""

    track_workflow: Optional[bool]
    """Whether to track detailed workflow information."""

    ui_analysis: Optional[Dict[str, Any]]
    """UI analysis results from the Navigator agent."""

    execution_time: Optional[float]
    """Total execution time for the task."""

    execution_mode: Optional[str]
    """Execution mode: 'live' (real device) or 'simulation' (dry run)."""

    spoken_response: Optional[str]
    """Final spoken response to the user."""

    spoken_audio: Optional[str]
    """Base64-encoded audio data for the spoken response."""

    spoken_audio_format: Optional[str]
    """MIME type for the spoken audio payload (e.g., 'audio/wav')."""

    # Intelligent agent routing
    used_agents: Optional[List[str]]
    """List of agents that were actually used for this task."""

    intent_classification: Optional[Dict[str, Any]]
    """Fuzzy classification results for intelligent routing."""

    execution_path: Optional[str]
    """The execution path taken (e.g., 'direct_response', 'simple_execution', 'full_workflow')."""

    skipped_steps: Optional[List[str]]
    """List of processing steps that were skipped due to intelligent routing."""

    input_type: Optional[str]
    """Type of input (voice, text, etc.)."""

    # Parallel processing fields
    validation_result: Optional[Dict[str, Any]]
    """Result from intent validation (from Validator agent)."""

    parallel_execution_time: Optional[float]
    """Time taken for parallel processing node."""

    screen_description: Optional[str]
    """Natural language description of the screen (from Screen Reader agent)."""

    # Note: Deprecated - replaced by Perception Controller (see UI Perception Blueprint)
    # Legacy UI modality fields - modality selection must be handled by
    # Perception Controller, not graph nodes or agents.
    ui_mode: Optional[str]
    """DEPRECATED: UI modality - must be determined by Perception Controller."""

    ui_confidence: Optional[float]
    """DEPRECATED: UI confidence - must be provided by Perception Controller."""

    visual_reference: Optional[bool]
    """DEPRECATED: Visual reference flag - must be determined by Perception Controller."""

    escalation_count: Optional[int]
    """DEPRECATED: Escalation count - must be tracked by Perception Controller."""

    # Conversation Context (NEW)
    conversation_turn: Optional[int]
    """Turn number in current conversation session (0 = first turn)."""

    has_introduced: Optional[bool]
    """Whether AURA has introduced itself in this session."""

    last_interaction_time: Optional[float]
    """Timestamp of last user interaction (for session timeout detection)."""

    is_follow_up: Optional[bool]
    """Whether this is a follow-up message (within 60 seconds of previous)."""

    # Perception Controller (NEW)
    perception_bundle: Optional[Any]
    """PerceptionBundle object from Perception Controller containing UI data, screenshot, modality, etc."""

    snapshot_id: Optional[str]
    """Unique identifier for the perception snapshot."""

    perception_modality: Optional[str]
    """Modality used for perception (hybrid, tree_only, screenshot_only)."""

    # Multi-Step Execution Support (NEW)
    pending_steps: Optional[List[Dict[str, Any]]]
    """Remaining steps to execute from parameters.steps in multi-action commands."""

    multi_step_index: Optional[int]
    """Current index in multi-step execution (0 = primary action, 1+ = secondary steps)."""

    multi_step_total: Optional[int]
    """Total number of steps in multi-step command."""

    multi_step_results: Optional[List[Dict[str, Any]]]
    """Results from each step in multi-step execution."""

    original_intent: Optional[Dict[str, Any]]
    """Original intent saved for multi-step commands (primary action + all steps)."""

    # Goal-Driven Execution State (NEW)
    agent_state: Optional[Any]
    """AgentState object for goal-driven execution with retry strategies and validation."""

    validation_routing: Optional[str]
    """Routing hint from validate_outcome_node (success/retry/abort)."""

    original_request: Optional[str]
    """Original user request text for goal tracking."""

    retry_action: Optional[Dict[str, Any]]
    """Retry action details from retry_router_node."""

    goal_status: Optional[str]
    """Current goal status (in_progress/completed/aborted)."""

    goal_summary: Optional[str]
    """Human-readable summary of the full goal (for context-aware responses)."""