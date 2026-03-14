"""
Performance Tracker - Execution timeline visualization for debugging.

Provides context managers and decorators to track execution time
of different phases in the AURA pipeline.
"""

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable, Dict, List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)

# Import unified logger for cross-referencing
try:
    from utils.unified_logger import get_unified_logger
    UNIFIED_LOGGER_AVAILABLE = True
except ImportError:
    UNIFIED_LOGGER_AVAILABLE = False


@dataclass
class PerfEvent:
    """A single performance event in the timeline."""
    
    name: str
    start: float
    end: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    children: List["PerfEvent"] = field(default_factory=list)
    error: Optional[str] = None
    
    @property
    def duration_ms(self) -> float:
        """Duration in milliseconds."""
        if self.end == 0.0:
            return 0.0
        return (self.end - self.start) * 1000
    
    @property
    def duration_str(self) -> str:
        """Human-readable duration."""
        ms = self.duration_ms
        if ms < 1000:
            return f"{ms:.1f}ms"
        return f"{ms/1000:.2f}s"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "duration_ms": round(self.duration_ms, 2),
            "metadata": self.metadata,
            "error": self.error,
            "children": [c.to_dict() for c in self.children] if self.children else None,
        }


class PerfTracker:
    """
    Track execution performance across multiple phases.
    
    Usage:
        perf = PerfTracker()
        
        with perf.track("Phase 1"):
            do_something()
        
        with perf.track("Phase 2", key="value"):
            with perf.track("Nested"):
                do_nested()
        
        print(perf.get_summary())
    """
    
    def __init__(self, name: str = "Execution"):
        self.name = name
        self.events: List[PerfEvent] = []
        self._stack: List[PerfEvent] = []
        self.start_time = time.time()
        self.end_time: Optional[float] = None
    
    @contextmanager
    def track(self, name: str, **metadata):
        """
        Track execution time of a code block.
        
        Args:
            name: Name of the phase being tracked.
            **metadata: Additional metadata to attach.
        
        Yields:
            PerfEvent being tracked (allows adding more metadata).
        """
        event = PerfEvent(name=name, start=time.time(), metadata=metadata)
        
        # Add to parent's children if nested
        if self._stack:
            self._stack[-1].children.append(event)
        else:
            self.events.append(event)
        
        self._stack.append(event)
        
        try:
            yield event
        except Exception as e:
            event.error = str(e)
            raise
        finally:
            event.end = time.time()
            self._stack.pop()
    
    def finalize(self):
        """Mark tracker as complete."""
        self.end_time = time.time()
    
    @property
    def total_duration_ms(self) -> float:
        """Total tracked duration in milliseconds."""
        end = self.end_time or time.time()
        return (end - self.start_time) * 1000
    
    def get_timeline(self) -> List[Dict[str, Any]]:
        """Get flat timeline of all events."""
        return [e.to_dict() for e in self.events]
    
    def get_summary(self) -> Dict[str, Any]:
        """Get performance summary."""
        self.finalize()
        
        # Calculate phase durations
        phase_times = {}
        for event in self.events:
            phase_times[event.name] = event.duration_ms
        
        # Find slowest phase
        slowest = max(self.events, key=lambda e: e.duration_ms) if self.events else None
        
        return {
            "name": self.name,
            "total_ms": round(self.total_duration_ms, 2),
            "phases": phase_times,
            "slowest_phase": slowest.name if slowest else None,
            "slowest_ms": round(slowest.duration_ms, 2) if slowest else 0,
            "timeline": self.get_timeline(),
        }
    
    def log_summary(self, log_level: str = "info"):
        """Log performance summary."""
        summary = self.get_summary()
        
        lines = [f"⏱️ {self.name} completed in {summary['total_ms']:.1f}ms"]
        
        for event in self.events:
            prefix = "  └─" if event == self.events[-1] else "  ├─"
            status = "❌" if event.error else "✓"
            lines.append(f"{prefix} {status} {event.name}: {event.duration_str}")
            
            for child in event.children:
                child_prefix = "      └─" if child == event.children[-1] else "      ├─"
                child_status = "❌" if child.error else "✓"
                lines.append(f"{child_prefix} {child_status} {child.name}: {child.duration_str}")
        
        message = "\n".join(lines)
        
        if log_level == "debug":
            logger.debug(message)
        else:
            logger.info(message)
        
        # Send to unified logger
        if UNIFIED_LOGGER_AVAILABLE:
            try:
                unified = get_unified_logger()
                unified.add(
                    message=f"Performance: {self.name} ({summary['total_ms']:.1f}ms)",
                    level="INFO" if log_level == "info" else "DEBUG",
                    source="perf",
                    context={
                        "total_ms": summary['total_ms'],
                        "phases": summary['phases'],
                        "slowest": summary.get('slowest_phase'),
                    }
                )
            except Exception as e:
                logger.debug(f"Could not send perf to unified logger: {e}")
        
        return summary


def track_async(name: str = None, **default_metadata):
    """
    Decorator to track async function execution time.
    
    Usage:
        @track_async("API Call")
        async def call_api():
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            tracker_name = name or func.__name__
            start = time.time()
            error = None
            
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                error = str(e)
                raise
            finally:
                duration_ms = (time.time() - start) * 1000
                status = "❌" if error else "✓"
                logger.debug(f"{status} {tracker_name}: {duration_ms:.1f}ms")
        
        return wrapper
    return decorator


def track_sync(name: str = None, **default_metadata):
    """
    Decorator to track sync function execution time.
    
    Usage:
        @track_sync("Processing")
        def process_data():
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            tracker_name = name or func.__name__
            start = time.time()
            error = None
            
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                error = str(e)
                raise
            finally:
                duration_ms = (time.time() - start) * 1000
                status = "❌" if error else "✓"
                logger.debug(f"{status} {tracker_name}: {duration_ms:.1f}ms")
        
        return wrapper
    return decorator


# Global tracker for request-scoped performance tracking
_request_tracker: Optional[PerfTracker] = None


def get_request_tracker() -> Optional[PerfTracker]:
    """Get current request's performance tracker."""
    return _request_tracker


def set_request_tracker(tracker: PerfTracker):
    """Set current request's performance tracker."""
    global _request_tracker
    _request_tracker = tracker


def clear_request_tracker():
    """Clear current request's performance tracker."""
    global _request_tracker
    _request_tracker = None
