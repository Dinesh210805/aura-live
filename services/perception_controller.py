"""
Perception Controller - Core orchestrator for UI perception.

Acts as the single authority deciding:
- What perception data is required
- When it must be captured
- Which modality to activate

Implements the Perception Controller from the UI Perception Pipeline blueprint.
"""

import uuid
import time
import asyncio
from typing import Any, Dict, List, Optional

from perception.models import (
    PerceptionBundle,
    PerceptionModality,
    ScreenMeta,
    ScreenshotPayload,
    UITreePayload,
)
from perception.selectors import select_modality
from perception.validators import validate_bundle_integrity
from services.real_accessibility import real_accessibility_service
from services.screenshot_service import get_screenshot_service
from services.ui_tree_service import get_ui_tree_service
from utils.logger import get_logger

logger = get_logger(__name__)

# TYPE_CHECKING import to avoid circular dependency
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from agents.visual_locator import ScreenVLM


class PerceptionController:
    """
    Core orchestrator for UI perception pipeline.

    This is the single authority for all perception decisions.
    """
    
    # Escalation ladder: Hybrid → Vision → Abort
    # Start with full context (HYBRID), escalate to vision-only for edge cases
    ESCALATION_ORDER = [
        PerceptionModality.HYBRID,
        PerceptionModality.VISION,
    ]
    MAX_RETRIES_PER_LEVEL = 2

    def __init__(self, screen_vlm: Optional["ScreenVLM"] = None):
        """Initialize Perception Controller.
        
        Args:
            screen_vlm: Optional ScreenVLM agent for VLM-based descriptions
        """
        self.ui_tree_service = get_ui_tree_service()
        self.screenshot_service = get_screenshot_service()
        self.screen_vlm = screen_vlm
        self.last_bundle: Optional[PerceptionBundle] = None
        
        # Visual description cache (screenshot_hash -> description)
        self._description_cache: Dict[str, str] = {}
        
        # Escalation state tracking
        self.escalation_level = 0  # Index into ESCALATION_ORDER
        self.retries_at_level = 0  # Retries at current level
        self.consecutive_failures = 0  # Total consecutive failures

    async def request_perception(
        self,
        intent: Dict[str, Any],
        action_type: str = "UI_ACTION",
        execution_history: Optional[List[Dict]] = None,
        retry_context: Optional[Dict] = None,
        app_category: Optional[str] = None,
        force_screenshot: bool = False,
        skip_description: bool = True,
        goal: str = "",
        subgoal_hint: str = "",
        recent_steps: str = "",
    ) -> PerceptionBundle:
        """
        Request perception data based on intent and context.

        This is the main entry point for perception requests.

        Args:
            intent: Parsed intent from Commander
            action_type: Type of action (UI_ACTION / NO_UI_ACTION)
            execution_history: Previous execution steps
            retry_context: Retry context if this is a retry
            app_category: App category if known

        Returns:
            PerceptionBundle with requested perception data

        Raises:
            ValueError: If perception cannot be obtained
        """
        try:
            # Generate request ID
            request_id = str(uuid.uuid4())[:8]
            reason = f"Action: {action_type or intent.get('action', 'unknown')}"

            # Check if this is a retry
            previous_failure = retry_context is not None and retry_context.get("failed", False)
            
            # Check if Android reported a validation failure that requires vision
            package_name = None
            if self.ui_tree_service.last_validation_failure:
                failure_info = self.ui_tree_service.last_validation_failure
                if failure_info.get("requires_vision", False):
                    logger.info(f"📱 Android validation failure suggests vision mode: {failure_info.get('reason')}")
                    package_name = failure_info.get("package_name")

            # Compute actual availability signals (not just optimistic assumptions)
            device_connected = real_accessibility_service.is_device_connected()
            ws_available = real_accessibility_service.has_websocket()
            ui_tree_available = device_connected and ws_available
            
            logger.debug(
                f"📊 Perception availability check: device_connected={device_connected}, "
                f"ws_available={ws_available}, ui_tree_available={ui_tree_available}"
            )
            
            # Early exit if device not connected
            if not device_connected:
                logger.error("❌ Device not connected, cannot request perception")
                raise ValueError(
                    "Device not connected. Please ensure Android device is connected via WebSocket."
                )

            # If we recently received empty screenshots, treat screenshot as temporarily unavailable
            # to prevent repeatedly choosing VISION and hard-failing.
            screenshot_available = device_connected and ws_available
            
            # Check if permission dialog is currently showing (don't try capture during dialog)
            if self.screenshot_service.is_permission_dialog_showing():
                screenshot_available = False
                logger.info(
                    "📸 Permission dialog in progress - skipping screenshot capture"
                )
            
            # Check for recent empty screenshot failures - but respect permission grants
            last_fail = getattr(self.screenshot_service, "last_capture_failure", None)
            permission_granted = getattr(self.screenshot_service, "_permission_granted", False)
            
            # If permission was granted, the previous failure is stale - clear it
            if permission_granted and last_fail:
                self.screenshot_service.last_capture_failure = None
                last_fail = None
                logger.debug("📸 Permission granted, cleared stale capture failure")
            
            if isinstance(last_fail, dict) and last_fail.get("reason") == "empty_screenshot":
                try:
                    age_s = time.time() - float(last_fail.get("at", 0))
                except Exception:
                    age_s = 0
                # Reduced from 60s to 15s - shorter cooldown to allow VLM fallback sooner
                if age_s < 15:
                    screenshot_available = False
                    logger.warning(
                        "📸 Screenshot capture recently failed (empty). Treating as unavailable for ~15s "
                        "(likely missing screen capture permission)."
                    )

            # Force screenshot for VLM fallback scenarios (bypasses availability check)
            if force_screenshot:
                screenshot_available = True
                logger.info("📸 Force screenshot requested for VLM fallback")
            
            # Select modality
            modality = select_modality(
                intent=intent,
                ui_tree_available=ui_tree_available,
                screenshot_available=screenshot_available,
                previous_failure=previous_failure,
                app_category=app_category,
                package_name=package_name,
            )

            logger.info(
                f"🎯 Perception request: request_id={request_id}, "
                f"modality={modality.value}, reason={reason}"
            )

            # Request perception data based on modality
            ui_tree: Optional[UITreePayload] = None
            screenshot: Optional[ScreenshotPayload] = None

            if modality in (PerceptionModality.UI_TREE, PerceptionModality.HYBRID):
                ui_tree = await self.ui_tree_service.request_ui_tree(request_id, reason)
                
                # RETRY LOGIC: If UI tree is empty (0 elements), wait and retry
                # This handles transient states like screen transitions
                max_retries = 3
                retry_delay = 0.5  # seconds
                retry_count = 0
                
                while ui_tree is not None and not ui_tree.elements and retry_count < max_retries:
                    retry_count += 1
                    logger.warning(
                        f"⚠️ UI tree returned empty, retrying ({retry_count}/{max_retries})..."
                    )
                    await asyncio.sleep(retry_delay)
                    ui_tree = await self.ui_tree_service.request_ui_tree(
                        f"{request_id}-r{retry_count}", 
                        f"{reason} (retry {retry_count})"
                    )
                
                if ui_tree is not None and not ui_tree.elements:
                    logger.warning(
                        f"⚠️ UI tree still empty after {max_retries} retries, trying screenshot fallback"
                    )
                    # Escalate to VISION mode as fallback
                    modality = PerceptionModality.VISION
                    ui_tree = None
                
                if ui_tree is None and modality == PerceptionModality.UI_TREE:
                    # If Android indicates UI tree is unreliable for this screen/app, escalate to vision.
                    failure_info = self.ui_tree_service.last_validation_failure or {}
                    if failure_info.get("requires_vision", False):
                        logger.info(
                            "📸 UI tree rejected by Android (requires_vision=True) → escalating to VISION"
                        )
                        modality = PerceptionModality.VISION
                    else:
                        raise ValueError("UI tree requested but retrieval failed")

            if modality in (PerceptionModality.VISION, PerceptionModality.HYBRID):
                screenshot = await self.screenshot_service.request_screenshot(request_id, reason)
                if screenshot is None and modality == PerceptionModality.VISION:
                    # Non-fatal fallback: if screenshot capture fails (often missing MediaProjection permission),
                    # degrade to UI tree so tasks can still proceed.
                    logger.warning(
                        "📸 Screenshot capture failed in VISION mode → falling back to UI_TREE"
                    )
                    modality = PerceptionModality.UI_TREE
                    if ui_tree is None:
                        ui_tree = await self.ui_tree_service.request_ui_tree(
                            request_id, "Fallback to UI tree after screenshot failure"
                        )
                    if ui_tree is None:
                        raise ValueError(
                            "Screenshot requested but capture failed (empty). "
                            "UI tree fallback also failed. Likely missing screen capture permission or device not ready."
                        )

            # Get screen metadata - prefer UI tree root bounds (most accurate)
            if ui_tree is not None:
                screen_meta = self._extract_screen_meta_from_ui_tree(ui_tree)
            elif screenshot is not None:
                screen_meta = ScreenMeta(
                    width=screenshot.screen_width,
                    height=screenshot.screen_height,
                    orientation=screenshot.orientation,
                    density_dpi=real_accessibility_service.device_info.get("density_dpi"),
                )
            else:
                screen_meta = self._extract_screen_meta_from_ui_tree(None)

            # Generate visual description if screenshot available and Screen Reader configured
            # Skip if skip_description=True (for routine element-finding calls)
            visual_description = None
            if skip_description:
                logger.debug("⏭️ Skipping screen description (skip_description=True)")
            elif screenshot and self.screen_vlm and modality in [PerceptionModality.VISION, PerceptionModality.HYBRID]:
                # Check cache first using screenshot hash
                import hashlib
                screenshot_hash = hashlib.md5(screenshot.screenshot_base64[:1000].encode()).hexdigest()
                
                if screenshot_hash in self._description_cache:
                    visual_description = self._description_cache[screenshot_hash]
                    logger.info(f"♻️ Reusing cached screen description ({len(visual_description)} chars)")
                else:
                    try:
                        # Create temporary bundle for Screen Reader (without visual_description)
                        temp_bundle = PerceptionBundle(
                            snapshot_id=str(uuid.uuid4()),
                            modality=modality,
                            ui_tree=ui_tree,
                            screenshot=screenshot,
                            screen_meta=screen_meta,
                            request_id=request_id,
                            reason=reason,
                        )
                        visual_description = await self.screen_vlm.describe_screen(
                            temp_bundle,
                            goal=goal,
                            subgoal_hint=subgoal_hint,
                            recent_steps=recent_steps,
                        )
                        
                        # Cache the description
                        self._description_cache[screenshot_hash] = visual_description
                        
                        # Limit cache size to last 10 descriptions
                        if len(self._description_cache) > 10:
                            oldest_key = next(iter(self._description_cache))
                            del self._description_cache[oldest_key]
                        
                        logger.info(f"🔍 Screen Reader generated description ({len(visual_description)} chars)")
                    except Exception as e:
                        logger.warning(f"⚠️ Screen Reader failed, continuing without description: {e}")

            # Create perception bundle with visual description
            bundle = PerceptionBundle(
                snapshot_id=str(uuid.uuid4()),
                modality=modality,
                ui_tree=ui_tree,
                screenshot=screenshot,
                screen_meta=screen_meta,
                visual_description=visual_description,
                request_id=request_id,
                reason=reason,
            )

            # Validate bundle integrity
            is_valid, validation_reason = validate_bundle_integrity(bundle)
            if not is_valid:
                # Provide user-friendly guidance for common issues
                if "no elements" in validation_reason.lower():
                    raise ValueError(
                        "I can't see your phone screen. Please check:\n"
                        "• Is your phone screen ON and unlocked?\n"
                        "• Is the AURA app's Accessibility Service enabled?\n"
                        "• Try opening the AURA app on your phone."
                    )
                raise ValueError(f"Perception bundle validation failed: {validation_reason}")

            self.last_bundle = bundle
            logger.info(
                f"✅ Perception bundle created: snapshot_id={bundle.snapshot_id}, "
                f"modality={modality.value}"
            )

            return bundle

        except Exception as e:
            logger.error(f"❌ Perception request failed: {e}")
            raise

    def _extract_screen_meta_from_ui_tree(self, ui_tree: Optional[UITreePayload]) -> ScreenMeta:
        """
        Extract screen dimensions from UI tree root element bounds.
        
        The root element's bounds always represent the full screen dimensions,
        which is more reliable than device-reported values.
        
        Args:
            ui_tree: UI tree payload with elements
            
        Returns:
            ScreenMeta with accurate screen dimensions
        """
        # Try to get dimensions from UI tree root element (most accurate)
        if ui_tree and ui_tree.elements:
            root = ui_tree.elements[0]
            bounds = root.get("bounds", {})
            width = bounds.get("right", 0)
            height = bounds.get("bottom", 0)
            
            if width > 0 and height > 0:
                logger.info(f"📐 Screen meta from UI tree root: {width}x{height}")
                return ScreenMeta(
                    width=width,
                    height=height,
                    orientation="portrait" if height > width else "landscape",
                    density_dpi=real_accessibility_service.device_info.get("density_dpi"),
                )
        
        # Fallback to device_info
        device_info = real_accessibility_service.device_info
        width = device_info.get("screen_width", 1080)
        height = device_info.get("screen_height", 1920)
        logger.warning(f"⚠️ Using device_info screen size (UI tree unavailable): {width}x{height}")
        
        return ScreenMeta(
            width=width,
            height=height,
            orientation="portrait",
            density_dpi=device_info.get("density_dpi"),
        )

    async def _get_screen_meta(self) -> ScreenMeta:
        """
        Get screen metadata from device.

        Returns:
            ScreenMeta with screen dimensions and properties
        """
        try:
            if real_accessibility_service.is_device_connected():
                # Get screen info from device_info directly (already set on connection)
                device_info = real_accessibility_service.device_info
                width = device_info.get("screen_width", 1080)
                height = device_info.get("screen_height", 1920)
                density_dpi = device_info.get("density_dpi")
                
                logger.debug(f"📐 Screen meta from device: {width}x{height}")
                
                return ScreenMeta(
                    width=width,
                    height=height,
                    orientation="portrait",
                    density_dpi=density_dpi,
                )
            else:
                # Default screen metadata if device not connected
                logger.warning("⚠️ Device not connected, using default screen size 1080x1920")
                return ScreenMeta(width=1080, height=1920, orientation="portrait")
        except Exception as e:
            logger.warning(f"⚠️ Failed to get screen info: {e}, using defaults")
            return ScreenMeta(width=1080, height=1920, orientation="portrait")

    def invalidate_bundle(self, reason: str = "UI action executed"):
        """
        Invalidate the last perception bundle.

        Called when a UI action is executed, making the bundle stale.

        Args:
            reason: Reason for invalidation
        """
        if self.last_bundle:
            logger.info(
                f"🔄 Invalidating bundle: snapshot_id={self.last_bundle.snapshot_id}, "
                f"reason={reason}"
            )
            self.last_bundle = None

    def get_last_bundle(self) -> Optional[PerceptionBundle]:
        """
        Get the last perception bundle (if still valid).

        Returns:
            Last bundle or None if invalid/not available
        """
        if self.last_bundle and self.last_bundle.is_valid():
            return self.last_bundle
        return None

    def escalate(self, failure_reason: str = "perception failed") -> bool:
        """
        Escalate to next modality level after failure.
        
        Implements: Tree → Vision → Hybrid → Abort
        
        Args:
            failure_reason: Why escalation is needed
        
        Returns:
            True if escalation successful, False if should abort
        """
        self.consecutive_failures += 1
        self.retries_at_level += 1
        
        if self.retries_at_level >= self.MAX_RETRIES_PER_LEVEL:
            # Move to next escalation level
            self.escalation_level += 1
            self.retries_at_level = 0
            
            if self.escalation_level >= len(self.ESCALATION_ORDER):
                logger.error(
                    f"❌ Escalation exhausted after {self.consecutive_failures} failures. "
                    f"Last failure: {failure_reason}. ABORTING."
                )
                return False
            
            next_modality = self.ESCALATION_ORDER[self.escalation_level]
            logger.warning(
                f"🔺 Escalating to {next_modality.value} (level {self.escalation_level}) "
                f"due to: {failure_reason}"
            )
        else:
            current = self.ESCALATION_ORDER[self.escalation_level]
            logger.info(
                f"🔄 Retrying {current.value} ({self.retries_at_level}/{self.MAX_RETRIES_PER_LEVEL})"
            )
        
        return True

    def reset_escalation(self):
        """Reset escalation state after successful perception."""
        if self.consecutive_failures > 0:
            logger.info(
                f"✅ Perception succeeded, resetting escalation "
                f"(was at level {self.escalation_level}, {self.consecutive_failures} failures)"
            )
        self.escalation_level = 0
        self.retries_at_level = 0
        self.consecutive_failures = 0

    def get_escalated_modality(self) -> Optional[PerceptionModality]:
        """
        Get the current escalated modality.
        
        Returns:
            Current modality based on escalation level, or None if should abort
        """
        if self.escalation_level >= len(self.ESCALATION_ORDER):
            return None
        return self.ESCALATION_ORDER[self.escalation_level]

    def should_abort(self) -> bool:
        """Check if perception should be aborted due to escalation exhaustion."""
        return self.escalation_level >= len(self.ESCALATION_ORDER)


# Global instance (initialized without screen_vlm)
_perception_controller: Optional[PerceptionController] = None


def get_perception_controller(screen_vlm: Optional["ScreenVLM"] = None) -> PerceptionController:
    """Get the global perception controller instance.
    
    Args:
        screen_vlm: Optional ScreenVLM agent (only used on first call)
        
    Returns:
        Global PerceptionController singleton
    """
    global _perception_controller
    if _perception_controller is None:
        _perception_controller = PerceptionController(screen_vlm=screen_vlm)
    return _perception_controller
