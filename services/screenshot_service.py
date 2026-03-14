"""
Screenshot Service - Captures screenshots from Android.

Implements the Screenshot Capture contract from the blueprint.
"""

import asyncio
import time
from typing import Dict, Optional, Tuple

from perception.models import ScreenshotPayload
from services.real_accessibility import real_accessibility_service
from utils.logger import get_logger

# Timeout configuration (Android timeout must be < backend timeout)
BACKEND_SCREENSHOT_TIMEOUT_SEC = 15.0  # Backend waits up to 15s for Android response (apps can take 10-15s after launch)
LATE_RESPONSE_BUFFER_SEC = 10.0  # Keep timed-out requests for 10s to catch late responses
PERMISSION_REQUEST_COOLDOWN_SEC = 30.0  # Don't request permission more than once per 30s
PERMISSION_DIALOG_TIMEOUT_SEC = 60.0  # Assume dialog closed after 60s if no response
SCREENSHOT_RETRY_DELAY_SEC = 1.5  # Delay before retrying an empty screenshot
EMPTY_THRESHOLD_BEFORE_PERMISSION_REQUEST = 2  # Number of consecutive empties before requesting permission

logger = get_logger(__name__)


class ScreenshotService:
    """
    Service for capturing screenshots from Android device.

    Implements pull-based capture - Android never pushes screenshots autonomously.
    """

    def __init__(self):
        """Initialize Screenshot Service."""
        self.last_request_id: Optional[str] = None
        self.pending_requests: Dict[str, asyncio.Future] = {}
        # Track timed-out requests: {request_id: (future, timeout_timestamp)}
        self.timed_out_requests: Dict[str, Tuple[asyncio.Future, float]] = {}
        # Track recent capture failures (commonly indicates missing MediaProjection permission)
        self.last_capture_failure: Optional[Dict[str, object]] = None
        # Cleanup task started flag (lazy initialization when event loop is running)
        self._cleanup_task_started: bool = False
        
        # Permission dialog state tracking
        self._permission_dialog_in_progress: bool = False
        self._permission_dialog_started_at: Optional[float] = None
        self._last_permission_request_at: Optional[float] = None
        self._permission_granted: bool = False  # Set True when Android confirms grant
        self._consecutive_empty_count: int = 0  # Track consecutive empty screenshots

        # Event set when permission is granted — allows efficient waiting without polling.
        # Created lazily because asyncio.Event() must be created on the running event loop.
        self._permission_event: Optional[asyncio.Event] = None

        # How many automation tasks are currently executing.
        # While > 0, _auto_request_permission() is suppressed so the dialog never
        # interrupts a running task (pre-flight check handles it instead).
        self._active_task_count: int = 0

    async def request_screenshot(
        self, request_id: str, reason: str
    ) -> Optional[ScreenshotPayload]:
        """
        Request screenshot from Android device via WebSocket.

        Backend -> Android:
        REQUEST_SCREENSHOT { request_id, reason }

        Android must:
        - Capture via MediaProjection
        - Preserve native resolution
        - Attach metadata (width, height, orientation, timestamp)
        - Return immediately

        Args:
            request_id: Unique request identifier
            reason: Reason for requesting screenshot

        Returns:
            ScreenshotPayload or None if request failed/timed out
        """
        try:
            # Lazy start cleanup task (only when event loop is running)
            if not self._cleanup_task_started:
                asyncio.create_task(self._cleanup_expired_timeouts())
                self._cleanup_task_started = True
            
            if not real_accessibility_service.is_device_connected():
                logger.warning("❌ Device not connected, cannot request screenshot")
                return None

            if not real_accessibility_service.has_websocket():
                logger.error("❌ WebSocket not available, cannot request screenshot")
                return None

            logger.info(f"📸 Requesting screenshot: request_id={request_id}, reason={reason}")

            # Create future to wait for response
            future = asyncio.get_running_loop().create_future()
            self.pending_requests[request_id] = future

            # Send request via WebSocket
            websocket = real_accessibility_service._websocket
            await websocket.send_json({
                "type": "request_screenshot",
                "request_id": request_id,
                "reason": reason,
            })

            # Wait for response with timeout (must exceed Android's internal timeout)
            try:
                screenshot_data = await asyncio.wait_for(future, timeout=BACKEND_SCREENSHOT_TIMEOUT_SEC)
                logger.info(f"✅ Screenshot received: request_id={request_id}")
                parsed = self._parse_screenshot_response(screenshot_data)
                if parsed is None:
                    # First attempt empty - retry once after a short delay
                    # MediaProjection may need time after permission grant or app switch
                    self._consecutive_empty_count += 1
                    logger.info(
                        f"📸 Screenshot empty (attempt 1), retrying after {SCREENSHOT_RETRY_DELAY_SEC}s... "
                        f"(consecutive empties: {self._consecutive_empty_count})"
                    )
                    await asyncio.sleep(SCREENSHOT_RETRY_DELAY_SEC)
                    
                    # Retry: send a new request
                    retry_id = f"{request_id}_retry"
                    retry_future = asyncio.get_running_loop().create_future()
                    self.pending_requests[retry_id] = retry_future
                    await websocket.send_json({
                        "type": "request_screenshot",
                        "request_id": retry_id,
                        "reason": f"{reason} (retry)",
                    })
                    try:
                        retry_data = await asyncio.wait_for(retry_future, timeout=BACKEND_SCREENSHOT_TIMEOUT_SEC)
                        parsed = self._parse_screenshot_response(retry_data)
                    except asyncio.TimeoutError:
                        logger.warning(f"⏱️ Screenshot retry also timed out: {retry_id}")
                    finally:
                        self.pending_requests.pop(retry_id, None)
                    
                    if parsed is None:
                        self.last_capture_failure = {
                            "request_id": request_id,
                            "reason": "empty_screenshot",
                            "at": time.time(),
                            "capture_reason": reason,
                        }
                        # Only request permission after multiple consecutive empties
                        if self._consecutive_empty_count >= EMPTY_THRESHOLD_BEFORE_PERMISSION_REQUEST:
                            logger.warning(
                                f"📸 {self._consecutive_empty_count} consecutive empty screenshots - "
                                "likely missing permission"
                            )
                            if not self._permission_granted:
                                asyncio.create_task(self._auto_request_permission())
                    else:
                        self._consecutive_empty_count = 0
                        self.last_capture_failure = None
                else:
                    self._consecutive_empty_count = 0
                    self.last_capture_failure = None
                return parsed
            except asyncio.TimeoutError:
                logger.warning(
                    f"⏱️  Screenshot request timed out after {BACKEND_SCREENSHOT_TIMEOUT_SEC}s: "
                    f"request_id={request_id}. Buffering for late response."
                )
                # Move to timed_out buffer instead of discarding (handles late Android responses)
                future = self.pending_requests.pop(request_id, None)
                if future:
                    timeout_ts = time.time() + LATE_RESPONSE_BUFFER_SEC
                    self.timed_out_requests[request_id] = (future, timeout_ts)
                    logger.debug(
                        f"📦 Buffered timed-out request {request_id} for {LATE_RESPONSE_BUFFER_SEC}s"
                    )
                self.last_capture_failure = {
                    "request_id": request_id,
                    "reason": "timeout",
                    "at": time.time(),
                    "capture_reason": reason,
                }
                return None
            finally:
                # Don't pop here - already handled in except block or handle_screenshot_response
                pass

        except Exception as e:
            logger.error(f"❌ Failed to request screenshot: {e}")
            self.pending_requests.pop(request_id, None)
            return None

    def handle_screenshot_response(self, request_id: str, screenshot_data: Dict) -> bool:
        """
        Handle incoming screenshot response from Android.

        Called by WebSocket router when screenshot_response message is received.

        Args:
            request_id: Request ID that this response corresponds to
            screenshot_data: Screenshot data from Android

        Returns:
            True if response was handled, False if no pending request
        """
        logger.info(f"📥 Received screenshot response: request_id={request_id}, pending={list(self.pending_requests.keys())}")
        
        # Check both active and timed-out requests
        is_late = False
        future = None
        
        if request_id in self.pending_requests:
            future = self.pending_requests.pop(request_id)
            is_late = False
        elif request_id in self.timed_out_requests:
            future, _ = self.timed_out_requests.pop(request_id)
            is_late = True
            logger.info(f"📬 Late screenshot response arrived for {request_id}")
        else:
            logger.warning(
                f"⚠️ No pending screenshot request for {request_id} "
                f"(discarded or never existed)"
            )
            return False
        
        if not future.done():
            logger.info(f"✅ Matched screenshot request {request_id}")
            future.set_result(screenshot_data)
            return True
        else:
            if is_late:
                logger.warning(
                    f"⚠️ Late response for {request_id} arrived after timeout. "
                    f"Original request already failed."
                )
            else:
                logger.warning(f"⚠️ Screenshot future for {request_id} already done")
            return False

    def _parse_screenshot_response(self, data: Dict) -> Optional[ScreenshotPayload]:
        """
        Parse screenshot response from Android into ScreenshotPayload.

        Args:
            data: Raw screenshot data from Android

        Returns:
            Parsed ScreenshotPayload or None if parsing failed
        """
        try:
            screenshot_base64 = data.get("screenshot_base64", data.get("screenshot", ""))
            screen_width = data.get("screen_width", data.get("screenWidth", 1080))
            screen_height = data.get("screen_height", data.get("screenHeight", 1920))
            orientation = data.get("orientation", "portrait")
            timestamp = data.get("timestamp", int(time.time() * 1000))
            
            # Check for explicit error from Android (permission revoked, lifecycle invalidation)
            if "error" in data:
                error_msg = data["error"]
                logger.error(f"❌ Android screenshot error: {error_msg}")
                if "permission" in error_msg.lower() or "mediaprojection" in error_msg.lower():
                    logger.error(
                        "🔒 MediaProjection permission invalidated (app backgrounded or revoked). "
                        "Re-granting required."
                    )
                    self.mark_permission_invalidated()
                # Auto-request permission
                asyncio.create_task(self._auto_request_permission())
                return None

            if not screenshot_base64:
                # Android responded but didn't provide image bytes.
                # This can happen when MediaProjection hasn't captured a frame yet
                # (no screen change since last capture) or permission is missing.
                # Don't immediately invalidate permission - let the caller handle retries.
                logger.warning(
                    "⚠️ Screenshot data is empty (no frames available or permission missing)"
                )
                return None
            
            # Success! Mark permission as working
            self._permission_granted = True
            self._permission_dialog_in_progress = False

            payload = ScreenshotPayload(
                screenshot_base64=screenshot_base64,
                screen_width=screen_width,
                screen_height=screen_height,
                orientation=orientation,
                timestamp=timestamp,
            )
            
            # Cache in real_accessibility_service for API access
            try:
                from services.real_accessibility import RealScreenshotData, real_accessibility_service
                real_accessibility_service.last_screenshot = RealScreenshotData(
                    screenshot=screenshot_base64,
                    screenWidth=screen_width,
                    screenHeight=screen_height,
                    timestamp=timestamp,
                    uiElements=[],  # UI elements fetched separately
                )
                logger.info(f"📸 Screenshot cached in accessibility service")
            except Exception as cache_err:
                logger.warning(f"Failed to cache screenshot: {cache_err}")
            
            return payload

        except Exception as e:
            logger.error(f"❌ Failed to parse screenshot response: {e}")
            return None

    async def _cleanup_expired_timeouts(self) -> None:
        """Background task to clean up expired timed-out requests."""
        while True:
            try:
                await asyncio.sleep(5.0)  # Check every 5 seconds
                now = time.time()
                expired = [
                    req_id for req_id, (_, timeout_ts) in self.timed_out_requests.items()
                    if now > timeout_ts
                ]
                for req_id in expired:
                    self.timed_out_requests.pop(req_id, None)
                    logger.debug(f"🗑️ Cleaned up expired timeout buffer for {req_id}")
            except Exception as e:
                logger.error(f"Error in timeout cleanup task: {e}")
                await asyncio.sleep(5.0)
    
    async def _auto_request_permission(self) -> None:
        """
        Automatically request screen capture permission when we detect empty screenshots.
        
        This is called when Android responds with 0 bytes, which typically means
        MediaProjection permission has not been granted yet.
        
        Guards:
        - Permission dialog already in progress
        - Recently requested (cooldown period)
        - Permission already granted and not invalidated
        - A task is currently executing (pre-flight check owns permission during automation)
        """
        try:
            # Guard: never interrupt a running automation task
            if self._active_task_count > 0:
                logger.debug("📸 Suppressing mid-task permission request (task is active)")
                return

            now = time.time()
            
            # Guard: Permission already granted and working
            if self._permission_granted:
                logger.debug("📸 Permission already granted, not requesting again")
                return
            
            # Guard: Dialog still in progress (with timeout)
            if self._permission_dialog_in_progress:
                if self._permission_dialog_started_at:
                    elapsed = now - self._permission_dialog_started_at
                    if elapsed < PERMISSION_DIALOG_TIMEOUT_SEC:
                        logger.debug(
                            f"📸 Permission dialog in progress ({elapsed:.1f}s), waiting..."
                        )
                        return
                    else:
                        # Dialog timed out (user probably dismissed it without responding)
                        logger.warning(
                            f"📸 Permission dialog timed out after {elapsed:.1f}s, resetting state"
                        )
                        self._permission_dialog_in_progress = False
                        self._permission_dialog_started_at = None
            
            # Guard: Cooldown period
            if self._last_permission_request_at:
                since_last = now - self._last_permission_request_at
                if since_last < PERMISSION_REQUEST_COOLDOWN_SEC:
                    logger.debug(
                        f"📸 Permission cooldown active ({since_last:.1f}s < {PERMISSION_REQUEST_COOLDOWN_SEC}s)"
                    )
                    return
            
            logger.info("📸 Requesting screen capture permission from Android...")
            
            # Mark dialog as in progress BEFORE sending request
            self._permission_dialog_in_progress = True
            self._permission_dialog_started_at = now
            self._last_permission_request_at = now
            
            result = await real_accessibility_service.request_screen_capture_permission()
            
            if result.get("success"):
                logger.info(
                    "📸 Permission request sent! User should see a dialog on their device. "
                    "Tap 'Start now' or 'Allow' to enable screen capture."
                )
            else:
                logger.warning(f"📸 Failed to request permission: {result.get('error')}")
                # Reset state on failure so we can retry
                self._permission_dialog_in_progress = False
                
        except Exception as e:
            logger.warning(f"📸 Auto-permission request failed: {e}")
            self._permission_dialog_in_progress = False
    
    def handle_permission_result(self, granted: bool, error: Optional[str] = None) -> None:
        """
        Handle permission result notification from Android.
        
        Called by WebSocket router when Android sends screen_capture_permission_result.
        
        Args:
            granted: True if permission was granted
            error: Optional error message if denied/failed
        """
        self._permission_dialog_in_progress = False
        self._permission_dialog_started_at = None
        
        if granted:
            logger.info("📸 Screen capture permission GRANTED by user")
            self._permission_granted = True
            self.last_capture_failure = None  # Clear failure state
            # Wake up anything waiting on permission
            self._get_permission_event().set()
        else:
            logger.warning(f"📸 Screen capture permission DENIED: {error or 'User declined'}")
            self._permission_granted = False
            self._get_permission_event().clear()

    def _get_permission_event(self) -> asyncio.Event:
        """Return (lazily creating) the asyncio.Event for permission grant signalling."""
        if self._permission_event is None:
            self._permission_event = asyncio.Event()
            if self._permission_granted:
                self._permission_event.set()
        return self._permission_event

    async def wait_for_permission(self, timeout: float = 25.0) -> bool:
        """
        Await screen-capture permission grant.  Returns True when granted, False on timeout.
        Should only be called AFTER `request_screen_capture_permission()` has been sent.
        """
        if self._permission_granted:
            return True
        event = self._get_permission_event()
        event.clear()  # Reset in case it was set from a previous session
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return self._permission_granted
        except asyncio.TimeoutError:
            return False

    def mark_task_active(self) -> None:
        """Increment active-task counter — suppresses reactive permission popups."""
        self._active_task_count += 1

    def mark_task_done(self) -> None:
        """Decrement active-task counter."""
        self._active_task_count = max(0, self._active_task_count - 1)
    
    def is_permission_dialog_showing(self) -> bool:
        """Check if permission dialog is currently being shown to user."""
        if not self._permission_dialog_in_progress:
            return False
        
        # Check for timeout
        if self._permission_dialog_started_at:
            elapsed = time.time() - self._permission_dialog_started_at
            if elapsed >= PERMISSION_DIALOG_TIMEOUT_SEC:
                self._permission_dialog_in_progress = False
                return False
        
        return True
    
    def mark_permission_invalidated(self) -> None:
        """Mark that the MediaProjection permission has been invalidated (app backgrounded, etc)."""
        logger.info("📸 MediaProjection permission invalidated, will request again when needed")
        self._permission_granted = False
        self._get_permission_event().clear()


# Global instance
screenshot_service = ScreenshotService()


def get_screenshot_service() -> ScreenshotService:
    """Get the global screenshot service instance."""
    return screenshot_service
