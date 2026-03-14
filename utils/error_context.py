"""
Error Context Collector - Comprehensive error diagnostics for debugging.

Collects and structures all relevant context when errors occur,
making debugging significantly easier.
"""

import traceback
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from utils.logger import get_logger

if TYPE_CHECKING:
    from perception.models import PerceptionBundle
    from aura_graph.agent_state import Subgoal

logger = get_logger(__name__)


@dataclass
class ErrorContext:
    """
    Comprehensive error context for debugging.
    
    Collects all relevant state when an error occurs, making it
    easy to understand and reproduce issues.
    """
    
    # Error Details
    error_type: str
    error_message: str
    failed_at: str
    stack_trace: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # Agent State
    current_goal: Optional[str] = None
    current_subgoal: Optional[str] = None
    subgoal_index: Optional[int] = None
    total_subgoals: Optional[int] = None
    retry_count: int = 0
    actions_taken: int = 0
    
    # Perception State
    screenshot_available: bool = False
    screenshot_size: int = 0
    ui_tree_available: bool = False
    ui_tree_nodes: int = 0
    perception_mode: Optional[str] = None
    last_detection_count: int = 0
    
    # Execution State
    last_action_type: Optional[str] = None
    last_action_target: Optional[str] = None
    last_action_result: Optional[str] = None
    last_action_success: Optional[bool] = None
    
    # Device State
    device_connected: bool = False
    current_app: Optional[str] = None
    current_activity: Optional[str] = None
    screen_dimensions: Optional[tuple] = None
    
    # Model State
    llm_provider: Optional[str] = None
    vlm_provider: Optional[str] = None
    last_llm_latency_ms: Optional[float] = None
    last_vlm_latency_ms: Optional[float] = None
    
    # Recovery State
    recovery_attempted: bool = False
    recovery_strategy: Optional[str] = None
    recovery_result: Optional[str] = None
    
    # Additional Context
    session_id: Optional[str] = None
    user_utterance: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        result = {}
        for key, value in self.__dict__.items():
            if value is not None and value != {} and value != []:
                if isinstance(value, tuple):
                    result[key] = list(value)
                else:
                    result[key] = value
        return result
    
    def to_log_string(self) -> str:
        """Format as readable log string."""
        lines = [
            "=" * 60,
            f"❌ ERROR CONTEXT: {self.error_type}",
            "=" * 60,
            f"Message: {self.error_message}",
            f"Failed at: {self.failed_at}",
            f"Time: {self.timestamp}",
            "",
        ]
        
        # Agent State
        if self.current_goal or self.current_subgoal:
            lines.append("📋 Agent State:")
            if self.current_goal:
                lines.append(f"  Goal: {self.current_goal}")
            if self.current_subgoal:
                lines.append(f"  Subgoal [{self.subgoal_index}/{self.total_subgoals}]: {self.current_subgoal}")
            lines.append(f"  Actions: {self.actions_taken}, Retries: {self.retry_count}")
            lines.append("")
        
        # Perception State
        lines.append("🔍 Perception State:")
        lines.append(f"  Screenshot: {'✓' if self.screenshot_available else '✗'} ({self.screenshot_size} bytes)")
        lines.append(f"  UI Tree: {'✓' if self.ui_tree_available else '✗'} ({self.ui_tree_nodes} nodes)")
        if self.perception_mode:
            lines.append(f"  Mode: {self.perception_mode}")
        lines.append("")
        
        # Execution State  
        if self.last_action_type:
            lines.append("⚡ Last Action:")
            lines.append(f"  Type: {self.last_action_type}")
            if self.last_action_target:
                lines.append(f"  Target: {self.last_action_target}")
            lines.append(f"  Success: {'✓' if self.last_action_success else '✗'}")
            if self.last_action_result:
                lines.append(f"  Result: {self.last_action_result}")
            lines.append("")
        
        # Device State
        lines.append("📱 Device State:")
        lines.append(f"  Connected: {'✓' if self.device_connected else '✗'}")
        if self.current_app:
            lines.append(f"  App: {self.current_app}")
        if self.screen_dimensions:
            lines.append(f"  Screen: {self.screen_dimensions[0]}x{self.screen_dimensions[1]}")
        lines.append("")
        
        # Model State
        if self.llm_provider or self.vlm_provider:
            lines.append("🤖 Model State:")
            if self.llm_provider:
                lines.append(f"  LLM: {self.llm_provider}")
            if self.vlm_provider:
                lines.append(f"  VLM: {self.vlm_provider}")
            if self.last_llm_latency_ms:
                lines.append(f"  Last LLM latency: {self.last_llm_latency_ms:.0f}ms")
            lines.append("")
        
        # Stack Trace
        if self.stack_trace:
            lines.append("📜 Stack Trace:")
            for line in self.stack_trace.split("\n")[-10:]:
                lines.append(f"  {line}")
        
        lines.append("=" * 60)
        return "\n".join(lines)


class ErrorContextCollector:
    """
    Collects error context from various sources.
    
    Usage:
        collector = ErrorContextCollector()
        
        try:
            # ... code that might fail
        except Exception as e:
            context = collector.collect(
                error=e,
                bundle=perception_bundle,
                subgoal=current_subgoal,
            )
            logger.error(context.to_log_string())
    """
    
    def __init__(self):
        self._last_action: Optional[Dict[str, Any]] = None
        self._action_count = 0
        self._retry_count = 0
    
    def record_action(
        self,
        action_type: str,
        target: Optional[str] = None,
        success: bool = False,
        result: Optional[str] = None,
    ):
        """Record an action for error context."""
        self._action_count += 1
        self._last_action = {
            "type": action_type,
            "target": target,
            "success": success,
            "result": result,
        }
    
    def record_retry(self):
        """Record a retry attempt."""
        self._retry_count += 1
    
    def reset(self):
        """Reset action tracking for new goal."""
        self._last_action = None
        self._action_count = 0
        self._retry_count = 0
    
    def collect(
        self,
        error: Exception,
        failed_at: str = "unknown",
        bundle: Optional["PerceptionBundle"] = None,
        subgoal: Optional["Subgoal"] = None,
        goal_description: Optional[str] = None,
        total_subgoals: int = 0,
        subgoal_index: int = 0,
        session_id: Optional[str] = None,
        user_utterance: Optional[str] = None,
        **extra_metadata,
    ) -> ErrorContext:
        """
        Collect comprehensive error context.
        
        Args:
            error: The exception that occurred.
            failed_at: Description of where failure occurred.
            bundle: Current perception bundle.
            subgoal: Current subgoal being executed.
            goal_description: Overall goal description.
            total_subgoals: Total number of subgoals.
            subgoal_index: Index of current subgoal.
            session_id: Current session ID.
            user_utterance: Original user command.
            **extra_metadata: Additional context to include.
            
        Returns:
            ErrorContext with all collected information.
        """
        # Get stack trace
        stack_trace = traceback.format_exc()
        
        # Extract perception info
        screenshot_available = False
        screenshot_size = 0
        ui_tree_available = False
        ui_tree_nodes = 0
        perception_mode = None
        current_app = None
        screen_dims = None
        
        if bundle:
            screenshot_available = bundle.screenshot is not None
            screenshot_size = len(bundle.screenshot) if bundle.screenshot else 0
            ui_tree_available = bundle.ui_tree is not None
            if bundle.ui_tree:
                nodes = bundle.ui_tree.get("nodes", [])
                ui_tree_nodes = len(nodes) if isinstance(nodes, list) else 0
            perception_mode = getattr(bundle, "perception_mode", None)
            
            # Try to extract current app
            if bundle.ui_tree:
                current_app = bundle.ui_tree.get("packageName") or bundle.ui_tree.get("package")
            
            # Screen dimensions
            if hasattr(bundle, "screen_width") and hasattr(bundle, "screen_height"):
                screen_dims = (bundle.screen_width, bundle.screen_height)
        
        # Extract device info
        device_connected = False
        try:
            from services.real_accessibility import real_accessibility_service
            device_connected = real_accessibility_service.device_info is not None
        except Exception:
            pass
        
        # Extract model info
        llm_provider = None
        vlm_provider = None
        try:
            from config.settings import get_settings
            settings = get_settings()
            llm_provider = settings.default_llm_provider
            vlm_provider = settings.default_vlm_provider
        except Exception:
            pass
        
        # Build context
        context = ErrorContext(
            error_type=type(error).__name__,
            error_message=str(error),
            failed_at=failed_at,
            stack_trace=stack_trace,
            
            current_goal=goal_description,
            current_subgoal=subgoal.description if subgoal else None,
            subgoal_index=subgoal_index,
            total_subgoals=total_subgoals,
            retry_count=self._retry_count,
            actions_taken=self._action_count,
            
            screenshot_available=screenshot_available,
            screenshot_size=screenshot_size,
            ui_tree_available=ui_tree_available,
            ui_tree_nodes=ui_tree_nodes,
            perception_mode=perception_mode,
            
            last_action_type=self._last_action.get("type") if self._last_action else None,
            last_action_target=self._last_action.get("target") if self._last_action else None,
            last_action_result=self._last_action.get("result") if self._last_action else None,
            last_action_success=self._last_action.get("success") if self._last_action else None,
            
            device_connected=device_connected,
            current_app=current_app,
            screen_dimensions=screen_dims,
            
            llm_provider=llm_provider,
            vlm_provider=vlm_provider,
            
            session_id=session_id,
            user_utterance=user_utterance,
            metadata=extra_metadata,
        )
        
        return context


# Global collector instance
_error_collector: Optional[ErrorContextCollector] = None


def get_error_collector() -> ErrorContextCollector:
    """Get or create global error context collector."""
    global _error_collector
    if _error_collector is None:
        _error_collector = ErrorContextCollector()
    return _error_collector


def collect_error_context(error: Exception, **kwargs) -> ErrorContext:
    """
    Convenience function to collect error context.
    
    Usage:
        try:
            risky_operation()
        except Exception as e:
            ctx = collect_error_context(e, failed_at="risky_operation", bundle=bundle)
            logger.error(ctx.to_log_string())
    """
    collector = get_error_collector()
    ctx = collector.collect(error, **kwargs)
    
    # Send to unified logger
    try:
        from utils.unified_logger import get_unified_logger
        unified = get_unified_logger()
        unified.add(
            message=f"Error context: {ctx.error_type} at {ctx.failed_at}",
            level="ERROR",
            source="error",
            trace_id=ctx.session_id,
            context={
                "error_type": ctx.error_type,
                "error_message": ctx.error_message[:200],
                "failed_at": ctx.failed_at,
                "goal": ctx.goal_description,
            }
        )
    except Exception:
        pass  # Don't fail if unified logger has issues
    
    return ctx
