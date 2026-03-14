"""
Visual Feedback Service - Apple Intelligence style effects for automation.

Sends commands to Android companion app to show:
1. Edge glow effect (white with inward shadow on all 4 sides)
2. Tap ripple animations at touch points
"""

from typing import Any, Optional, Tuple
from utils.logger import get_logger

logger = get_logger(__name__)


class VisualFeedbackService:
    """Manages visual feedback overlays on Android device."""

    def __init__(self):
        self._websocket: Optional[Any] = None
        self._enabled: bool = True
        self._edge_glow_active: bool = False

    def set_websocket(self, websocket: Any):
        """Set active WebSocket connection."""
        self._websocket = websocket
        logger.info("✨ Visual feedback WebSocket connected")

    def clear_websocket(self):
        """Clear WebSocket connection."""
        self._websocket = None
        logger.info("✨ Visual feedback WebSocket disconnected")

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value
        logger.info(f"Visual feedback {'enabled' if value else 'disabled'}")

    async def show_edge_glow(self, duration_ms: int = 2000) -> bool:
        """
        Show Apple Intelligence style edge glow effect.
        
        White glow on all 4 edges with inward shadow.
        
        Args:
            duration_ms: How long to show the glow (default 2s)
        """
        if not self._enabled or not self._websocket:
            return False

        try:
            await self._websocket.send_json({
                "type": "visual_feedback",
                "effect": "edge_glow",
                "action": "show",
                "config": {
                    "color": "#FFFFFF",
                    "blur_radius": 30,
                    "spread": 15,
                    "duration_ms": duration_ms,
                    "fade_in_ms": 150,
                    "fade_out_ms": 300
                }
            })
            self._edge_glow_active = True
            logger.debug(f"✨ Edge glow shown for {duration_ms}ms")
            return True
        except Exception as e:
            logger.warning(f"Failed to show edge glow: {e}")
            return False

    async def hide_edge_glow(self) -> bool:
        """Hide edge glow immediately."""
        if not self._websocket:
            return False

        try:
            await self._websocket.send_json({
                "type": "visual_feedback",
                "effect": "edge_glow",
                "action": "hide"
            })
            self._edge_glow_active = False
            logger.debug("✨ Edge glow hidden")
            return True
        except Exception as e:
            logger.warning(f"Failed to hide edge glow: {e}")
            return False

    async def show_tap_ripple(
        self, 
        x: int, 
        y: int, 
        duration_ms: int = 400,
        color: str = "#FFFFFF"
    ) -> bool:
        """
        Show ripple animation at tap location.
        
        Args:
            x: X coordinate of tap
            y: Y coordinate of tap
            duration_ms: Animation duration
            color: Ripple color (default white)
        """
        if not self._enabled:
            logger.warning("Visual feedback disabled")
            return False
            
        if not self._websocket:
            logger.warning("No WebSocket connection for visual feedback")
            return False

        try:
            await self._websocket.send_json({
                "type": "visual_feedback",
                "effect": "tap_ripple",
                "action": "show",
                "config": {
                    "x": x,
                    "y": y,
                    "color": color,
                    "max_radius": 80,
                    "duration_ms": duration_ms,
                    "stroke_width": 4
                }
            })
            logger.debug(f"👆 Tap ripple at ({x}, {y})")
            return True
        except Exception as e:
            logger.warning(f"Failed to show tap ripple: {e}")
            return False

    async def show_automation_start(self) -> bool:
        """Show visual feedback when automation starts."""
        return await self.show_edge_glow(duration_ms=0)  # 0 = stay until hidden

    async def show_automation_end(self) -> bool:
        """Hide visual feedback when automation ends."""
        return await self.hide_edge_glow()

    async def show_tap_with_glow(self, x: int, y: int) -> bool:
        """Convenience method: show edge glow + tap ripple together."""
        glow_ok = await self.show_edge_glow(duration_ms=800)
        tap_ok = await self.show_tap_ripple(x, y)
        return glow_ok and tap_ok


# Singleton instance
_visual_feedback_service: Optional[VisualFeedbackService] = None


def get_visual_feedback_service() -> VisualFeedbackService:
    """Get or create the visual feedback service singleton."""
    global _visual_feedback_service
    if _visual_feedback_service is None:
        _visual_feedback_service = VisualFeedbackService()
    return _visual_feedback_service
