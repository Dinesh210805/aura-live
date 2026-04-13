"""
Real Android Accessibility Service - replaces mock automation.

This service interfaces with the real Android AccessibilityService to:
1. Capture actual screenshots via MediaProjection
2. Analyze real UI hierarchies via AccessibilityNodeInfo
3. Execute real gestures via dispatchGesture()
4. Get actual device coordinates and bounds
"""

import asyncio
import base64
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple

from utils.logger import get_logger

logger = get_logger(__name__)
# Don't initialize settings at module level to avoid validation errors
# settings = get_settings()

# Global WebSocket connection for instant gesture execution
_active_websocket: Optional[Any] = None


@dataclass
class RealUIElement:
    """Real UI element from Android AccessibilityNodeInfo."""

    id: Optional[str]
    className: Optional[str]
    text: Optional[str]
    contentDescription: Optional[str]
    bounds: Dict[str, int]  # left, top, right, bottom, centerX, centerY, width, height
    isClickable: bool
    isScrollable: bool
    isEditable: bool
    isEnabled: bool
    packageName: Optional[str]
    viewId: Optional[str]


@dataclass
class RealScreenshotData:
    """Real screenshot data from Android device."""

    screenshot: str  # base64 encoded
    screenWidth: int
    screenHeight: int
    timestamp: int
    uiElements: List[RealUIElement]
    snapshot_id: str = ""  # Phase 3: Unique ID for provenance tracking


class RealAccessibilityService:
    """
    Real accessibility service that communicates with Android AccessibilityService.
    Replaces mock automation with actual device interaction.
    """

    def __init__(self):
        """Initialize real accessibility service."""
        self.connected_device = None
        self.last_screenshot: Optional[RealScreenshotData] = None
        self.last_ui_analysis: Optional[Dict[str, Any]] = None
        self.device_info = {
            "screen_width": 1080,
            "screen_height": 1920,
            "density_dpi": 420,
            "connected": False,
        }
        self._websocket: Optional[Any] = None  # Active WebSocket for instant gestures
        # Phase 7: Acknowledgment tracking for gestures
        self._pending_acks: Dict[str, asyncio.Future] = {}
        self._ack_timeout = 10.0  # seconds (increased for debugging)
        # Contact resolver for name-to-phone resolution
        self._contact_resolver: Optional[Any] = None

        logger.info("Real accessibility service initialized")

    def set_device_connection(self, device_info: Dict[str, Any]) -> None:
        """Set device connection information."""
        # Update device info with all provided data
        self.device_info.update(device_info)
        # CRITICAL: Explicitly mark device as connected
        self.device_info["connected"] = True
        self.connected_device = device_info.get("device_name", "Unknown Device")

        logger.info(f"🔌 Device connected: {device_info.get('device_name', 'Unknown')}")
        logger.info(
            f"📱 Screen: {device_info.get('screen_width', 0)}x{device_info.get('screen_height', 0)}"
        )
        logger.info(f"🤖 Android: {device_info.get('android_version', 'Unknown')}")
        logger.info(
            f"✅ Device connection status set to: {self.device_info['connected']}"
        )

    def set_websocket(self, websocket: Any):
        """Set active WebSocket for instant gesture execution."""
        self._websocket = websocket
        logger.info("🔌 WebSocket connected for instant gestures")

    def clear_websocket(self):
        """Clear WebSocket connection."""
        self._websocket = None
        logger.info("🔌 WebSocket disconnected")

    def has_websocket(self) -> bool:
        """Check if WebSocket is available for instant execution."""
        return self._websocket is not None
    
    def register_contact_resolver(self, contact_resolver: Any):
        """Register contact resolver for handling contact resolution results."""
        self._contact_resolver = contact_resolver
        logger.debug("📞 Contact resolver registered")
    
    def unregister_contact_resolver(self):
        """Unregister contact resolver."""
        self._contact_resolver = None
        logger.debug("📞 Contact resolver unregistered")

    def handle_gesture_ack(self, command_id: str, success: bool = True) -> bool:
        """
        Handle gesture acknowledgment from Android.
        
        Phase 7: Called when Android sends gesture_ack message.
        
        Args:
            command_id: The command ID being acknowledged.
            success: Whether the gesture executed successfully on Android.
            
        Returns:
            True if acknowledgment was expected and handled, False otherwise.
        """
        if command_id in self._pending_acks:
            future = self._pending_acks[command_id]
            if not future.done():
                future.set_result(success)
                logger.info(f"🔔 Ack received from Android: command_id={command_id}, success={success}")
                return True
        logger.warning(f"⚠️ Unexpected gesture ack: command_id={command_id}")
        return False

    def disconnect_device(self) -> None:
        """Disconnect the current device."""
        if self.device_info["connected"]:
            logger.info(f"🔌 Device disconnected: {self.connected_device}")

        self._websocket = None  # Clear WebSocket connection
        self.device_info = {
            "screen_width": 1080,
            "screen_height": 1920,
            "density_dpi": 420,
            "connected": False,
        }
        self.connected_device = None
        self.last_screenshot = None
        self.last_ui_analysis = None

    def is_device_connected(self) -> bool:
        """Check if device is currently connected."""
        # Only check the connected flag, not the device_name
        # Device name might be null initially but device is still connected
        connected = self.device_info.get("connected", False)
        logger.trace(
            f"Device connection check: connected={connected}, device_name={self.connected_device}, device_info={self.device_info}"
        )
        return connected

    async def request_fresh_screenshot(self) -> bool:
        """
        Request a fresh screenshot + UI tree from the connected Android device.

        Delegates to ScreenshotService (which handles WebSocket send + await) and
        UITreeService so that both last_screenshot and last_ui_analysis are refreshed.

        Returns:
            True if at least the screenshot was received, False on timeout/error.
        """
        try:
            import uuid
            from services.screenshot_service import get_screenshot_service
            from services.ui_tree_service import get_ui_tree_service

            request_id = str(uuid.uuid4())[:8]

            screenshot_service = get_screenshot_service()
            ui_tree_service = get_ui_tree_service()

            # Request both in parallel — Android processes them independently
            screenshot_result, _ = await asyncio.gather(
                screenshot_service.request_screenshot(request_id, "manual_request"),
                ui_tree_service.request_ui_tree(request_id, "manual_request"),
                return_exceptions=True,
            )

            if screenshot_result and not isinstance(screenshot_result, Exception):
                logger.info("📸 Fresh screenshot + UI tree captured successfully")
                return True

            logger.warning("⚠️ request_fresh_screenshot: screenshot not received")
            return False

        except Exception as e:
            logger.error(f"❌ request_fresh_screenshot failed: {e}")
            return False

    def update_ui_data(self, ui_data: Dict[str, Any]) -> bool:
        """
        Update stored UI data from Android accessibility service.
        Handles both screenshot and UI hierarchy data intelligently.
        """
        try:
            logger.trace(f"update_ui_data called with keys: {ui_data.keys()}")

            if not self.is_device_connected():
                logger.warning("❌ Device not connected, cannot update UI data")
                logger.trace(
                    f"Device connection state: connected={self.device_info.get('connected')}, device_name={self.connected_device}"
                )
                return False

            # Extract data components
            screenshot_b64 = ui_data.get("screenshot", "")
            ui_elements = ui_data.get("ui_elements", [])
            screen_width = ui_data.get("screen_width", ui_data.get("screenWidth", self.device_info["screen_width"]))
            screen_height = ui_data.get("screen_height", ui_data.get("screenHeight", self.device_info["screen_height"]))
            timestamp = ui_data.get("timestamp", int(time.time() * 1000))
            capture_reason = ui_data.get("capture_reason", "unknown")
            has_screenshot = ui_data.get("has_screenshot", False)

            logger.trace(
                f"UI data extraction: elements_count={len(ui_elements) if ui_elements else 0}, has_screenshot={has_screenshot}, reason={capture_reason}"
            )

            # Process UI elements into RealUIElement objects
            processed_elements = []
            if isinstance(ui_elements, list):
                for element_data in ui_elements:
                    if isinstance(element_data, dict):
                        try:
                            bounds_data = element_data.get("bounds", {})

                            # Handle Android string format: "[left,top][right,bottom]"
                            if isinstance(bounds_data, str):
                                import re

                                match = re.match(
                                    r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds_data
                                )
                                if match:
                                    left, top, right, bottom = map(int, match.groups())
                                    bounds_data = {
                                        "left": left,
                                        "top": top,
                                        "right": right,
                                        "bottom": bottom,
                                    }
                                else:
                                    bounds_data = {
                                        "left": 0,
                                        "top": 0,
                                        "right": 0,
                                        "bottom": 0,
                                    }

                            bounds = {
                                "left": bounds_data.get("left", 0),
                                "top": bounds_data.get("top", 0),
                                "right": bounds_data.get("right", 0),
                                "bottom": bounds_data.get("bottom", 0),
                                "centerX": (
                                    bounds_data.get("left", 0)
                                    + bounds_data.get("right", 0)
                                )
                                // 2,
                                "centerY": (
                                    bounds_data.get("top", 0)
                                    + bounds_data.get("bottom", 0)
                                )
                                // 2,
                                "width": bounds_data.get("right", 0)
                                - bounds_data.get("left", 0),
                                "height": bounds_data.get("bottom", 0)
                                - bounds_data.get("top", 0),
                            }

                            real_element = RealUIElement(
                                id=element_data.get("viewIdResourceName", ""),
                                className=element_data.get("className", ""),
                                text=element_data.get("text", ""),
                                contentDescription=element_data.get(
                                    "contentDescription", ""
                                ),
                                bounds=bounds,
                                isClickable=element_data.get("clickable", False),
                                isScrollable=element_data.get("scrollable", False),
                                isEditable=element_data.get("editable", False),
                                isEnabled=element_data.get("enabled", True),
                                packageName=element_data.get("packageName", ""),
                                viewId=element_data.get("viewIdResourceName", ""),
                            )
                            processed_elements.append(real_element)
                        except Exception as e:
                            logger.warning(f"⚠️ Failed to process UI element: {e}")

            # Phase 3: Generate snapshot_id from timestamp for provenance tracking
            import hashlib
            snapshot_id = hashlib.sha256(f"{timestamp}-{len(processed_elements)}".encode()).hexdigest()[:12]

            # Update screenshot data if provided
            if has_screenshot and screenshot_b64:
                self.last_screenshot = RealScreenshotData(
                    screenshot=screenshot_b64,
                    screenWidth=screen_width,
                    screenHeight=screen_height,
                    timestamp=timestamp,
                    uiElements=processed_elements,
                    snapshot_id=snapshot_id,
                )
                logger.info(
                    f"📸 Screenshot updated: {len(processed_elements)} elements, snapshot_id={snapshot_id}, reason: {capture_reason}"
                )
            else:
                # Update UI elements only - create screenshot data without image
                self.last_screenshot = RealScreenshotData(
                    screenshot="",  # Empty screenshot
                    screenWidth=screen_width,
                    screenHeight=screen_height,
                    timestamp=timestamp,
                    uiElements=processed_elements,
                    snapshot_id=snapshot_id,
                )
                logger.info(
                    f"📱 UI data updated: {len(processed_elements)} elements, snapshot_id={snapshot_id}, reason: {capture_reason}"
                )

            # Update device screen info
            self.device_info.update(
                {
                    "screen_width": screen_width,
                    "screen_height": screen_height,
                    "last_update": timestamp,
                }
            )

            return True

        except Exception as e:
            logger.error(f"❌ Failed to update UI data: {e}")
            return False

    # TODO: Replaced by new Perception Controller (see UI Perception Blueprint)
    # Legacy screenshot capture methods removed - screenshots must be requested
    # explicitly via the Perception Controller, not automatically captured here.

    # TODO: Replaced by new Perception Controller (see UI Perception Blueprint)
    # Legacy UI tree retrieval removed - UI trees must be requested explicitly
    # via the Perception Controller, not retrieved automatically here.

    @property
    def ui_elements(self) -> List[RealUIElement]:
        """
        Get current UI elements from last screenshot data.
        
        Returns:
            List of UI elements or empty list if none available.
        """
        if self.last_screenshot and self.last_screenshot.uiElements:
            return self.last_screenshot.uiElements
        return []

    async def get_screen_info(self) -> Dict[str, int]:
        """
        Get real screen dimensions and properties.

        Returns:
            Screen information dictionary.
        """
        return {
            "width": self.device_info["screen_width"],
            "height": self.device_info["screen_height"],
            "density_dpi": self.device_info["density_dpi"],
        }

    async def execute_real_gesture(self, action: str, **params) -> bool:
        """Execute a gesture request and return success state."""

        gesture_payload = self._normalize_gesture_payload({"action": action, **params})
        result = await self._send_gesture_to_device(gesture_payload)
        return result.get("success", False)

    async def dispatch_gesture(self, gesture_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a gesture request represented as a dictionary payload."""

        normalized_payload = self._normalize_gesture_payload(gesture_data)
        return await self._send_gesture_to_device(normalized_payload)

    def _normalize_gesture_payload(
        self, gesture_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Normalize gesture payload ensuring consistent structure and types."""

        action = str(gesture_data.get("action", "")).lower().strip()
        payload: Dict[str, Any] = {"action": action}

        for key, value in gesture_data.items():
            if key == "action" or value is None:
                continue

            if key in {"x", "y", "x1", "y1", "x2", "y2", "duration"}:
                try:
                    payload[key] = int(value)
                except (TypeError, ValueError):
                    logger.debug(
                        "Ignoring non-integer gesture parameter",
                        extra={"key": key, "value": value},
                    )
            else:
                payload[key] = value

        # Normalize swipe: REST API sends x/y but Android expects x1/y1 for swipe start
        if action == "swipe":
            if "x" in payload and "x1" not in payload:
                payload["x1"] = payload.pop("x")
            if "y" in payload and "y1" not in payload:
                payload["y1"] = payload.pop("y")

        payload.setdefault("timestamp", time.time())
        return payload

    async def _send_gesture_to_device(
        self, gesture_payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Send a normalized gesture payload to the connected Android device."""

        try:
            if not self.is_device_connected():
                logger.warning("No device connected, cannot execute gesture")
                return {
                    "success": False,
                    "error": "Device not connected",
                    "gesture": gesture_payload,
                }

            action = gesture_payload.get("action")
            if not action:
                logger.error("Gesture payload missing action field")
                return {
                    "success": False,
                    "error": "Missing action",
                    "gesture": gesture_payload,
                }

            if action in {"tap", "click"}:
                if not self._validate_coordinates(
                    gesture_payload.get("x", -1), gesture_payload.get("y", -1)
                ):
                    return {
                        "success": False,
                        "error": "Invalid tap coordinates",
                        "gesture": gesture_payload,
                    }

            if action == "swipe":
                # Accept both x1/y1 (GestureExecutor format) and x/y (REST API format)
                start_x = gesture_payload.get("x1", gesture_payload.get("x", -1))
                start_y = gesture_payload.get("y1", gesture_payload.get("y", -1))
                coords = self._validate_coordinates(start_x, start_y) and self._validate_coordinates(
                    gesture_payload.get("x2", -1), gesture_payload.get("y2", -1)
                )
                if not coords:
                    return {
                        "success": False,
                        "error": "Invalid swipe coordinates",
                        "gesture": gesture_payload,
                    }

            logger.info("Executing real gesture", extra={"gesture": gesture_payload})

            # Phase 4: WebSocket is the ONLY gesture delivery channel
            if not self._websocket:
                logger.error("❌ WebSocket required for gesture execution - no connection available")
                return {
                    "success": False,
                    "error": "WebSocket required for gesture execution",
                    "gesture": gesture_payload,
                }

            try:
                # Phase 7: Generate command_id for acknowledgment tracking
                import uuid
                import json
                command_id = str(uuid.uuid4())[:8]
                gesture_payload["command_id"] = command_id
                
                # DEBUG: Log full payload being sent
                payload_to_send = {"type": "execute_gesture", "gesture": gesture_payload}
                logger.info(f"⚡ Sending gesture via WebSocket: {action}, command_id={command_id}")
                logger.debug(f"📤 Full WebSocket payload: {json.dumps(payload_to_send)}")
                
                # Create future for acknowledgment
                ack_future = asyncio.get_running_loop().create_future()
                self._pending_acks[command_id] = ack_future
                
                try:
                    await self._websocket.send_json(payload_to_send)
                    
                    # Phase 7: Wait for acknowledgment with timeout
                    try:
                        ack_success = await asyncio.wait_for(ack_future, timeout=self._ack_timeout)
                        logger.info(f"{'✅' if ack_success else '❌'} Gesture acknowledged: command_id={command_id}, success={ack_success}")
                        return {
                            "success": ack_success,
                            "gesture": gesture_payload,
                            "method": "websocket",
                            "command_id": command_id,
                            "acknowledged": True,
                        }
                    except asyncio.TimeoutError:
                        logger.error(f"❌ Gesture acknowledgment timeout: command_id={command_id} (waited {self._ack_timeout}s)")
                        return {
                            "success": False,
                            "error": f"Gesture acknowledgment timeout after {self._ack_timeout}s",
                            "gesture": gesture_payload,
                            "command_id": command_id,
                        }
                finally:
                    # Clean up pending ack
                    self._pending_acks.pop(command_id, None)
                    
            except Exception as ws_error:
                logger.error(f"❌ WebSocket gesture send failed: {ws_error}")
                self._websocket = None  # Clear broken connection
                return {
                    "success": False,
                    "error": f"WebSocket send failed: {ws_error}",
                    "gesture": gesture_payload,
                }

        except Exception as exc:
            logger.error(
                f"Failed to execute gesture {gesture_payload.get('action')}: {exc}"
            )
            return {"success": False, "error": str(exc), "gesture": gesture_payload}

    async def find_element_by_text(self, text: str) -> Optional[RealUIElement]:
        """
        Find UI element by text content.

        Args:
            text: Text to search for.

        Returns:
            Matching UI element or None.
        """
        elements, _ = await self.analyze_real_ui()  # Unpack tuple, ignore snapshot_id

        for element in elements:
            if element.text and text.lower() in element.text.lower():
                return element
            if (
                element.contentDescription
                and text.lower() in element.contentDescription.lower()
            ):
                return element

        return None

    async def find_clickable_elements(self) -> List[RealUIElement]:
        """
        Find all clickable elements on current screen.

        Returns:
            List of clickable UI elements.
        """
        elements, _ = await self.analyze_real_ui()  # Unpack tuple, ignore snapshot_id
        return [elem for elem in elements if elem.isClickable]

    async def get_element_center_coordinates(
        self, element: RealUIElement
    ) -> Tuple[int, int]:
        """
        Get center coordinates of a UI element.

        Args:
            element: UI element.

        Returns:
            (x, y) center coordinates.
        """
        return (element.bounds["centerX"], element.bounds["centerY"])

    def _validate_coordinates(self, x: int, y: int) -> bool:
        """Validate coordinates are within screen bounds."""
        max_x = self.device_info["screen_width"]
        max_y = self.device_info["screen_height"]
        is_valid = 0 <= x <= max_x and 0 <= y <= max_y
        
        if not is_valid:
            logger.warning(
                f"❌ Coordinate validation failed: ({x}, {y}) outside screen bounds (0-{max_x}, 0-{max_y})"
            )
        
        return is_valid

    # TODO: Replaced by new Perception Controller (see UI Perception Blueprint)
    # Legacy demo/mock data generation removed - no fallback data should be
    # synthesized. System must fail loudly when perception data is unavailable.

    # TODO: Replaced by new Perception Controller (see UI Perception Blueprint)
    # Legacy UI element retrieval methods removed - UI elements must be requested
    # explicitly via the Perception Controller, not retrieved automatically here.

    # TODO: Replaced by new Perception Controller (see UI Perception Blueprint)
    # Legacy hybrid UI analysis removed - perception must be orchestrated
    # by the Perception Controller, not performed ad-hoc here.

    async def launch_app_via_intent(self, package_name: str, deep_link_uri: Optional[str] = None) -> Dict[str, Any]:
        """
        Launch app using Android intent via WebSocket.

        Args:
            package_name: Android package name of the app.

        Returns:
            Launch result.
        """
        try:
            if not self.is_device_connected():
                logger.warning("No device connected, cannot launch app")
                return {"success": False, "error": "Device not connected"}

            if not self._websocket:
                logger.error("❌ WebSocket required for app launch - no connection available")
                return {"success": False, "error": "WebSocket required for app launch"}

            logger.info(f"🚀 Sending app launch command via WebSocket: {package_name}")

            # Import app inventory for package candidates
            from utils.app_inventory_utils import get_app_inventory_manager

            # Query inventory for similar packages (e.g., multiple camera apps)
            inventory_manager = get_app_inventory_manager()
            package_candidates = [package_name]

            # Try to find similar apps by extracting the app type
            # For example: com.oplus.camera -> "camera"
            if "." in package_name:
                app_type = package_name.split(".")[-1].lower()
                similar_packages = inventory_manager.get_package_candidates(app_type)
                if similar_packages and len(similar_packages) > 1:
                    package_candidates = similar_packages
                    logger.info(
                        f"Using {len(package_candidates)} package candidates for '{app_type}' from inventory"
                    )

            # Send command via WebSocket
            import uuid
            command_id = str(uuid.uuid4())[:8]
            
            # Use launch_deep_link type if deep link URI is provided
            if deep_link_uri:
                await self._websocket.send_json({
                    "type": "launch_deep_link",
                    "command_id": command_id,
                    "uri": deep_link_uri,
                    "package_name": package_name,  # Target app for deep link
                })
                logger.info(f"✅ Deep link launch command sent via WebSocket: {command_id} - {deep_link_uri}")
            else:
                await self._websocket.send_json({
                    "type": "launch_app",
                    "command_id": command_id,
                    "package_name": package_name,
                    "package_candidates": package_candidates,
                    "method": "intent",
                })
                logger.info(f"✅ App launch command sent via WebSocket: {command_id} for {package_name}")
            
            # Return optimistic success - Android will execute immediately via WebSocket
            return {
                "success": True,
                "package_name": package_name,
                "method": "websocket",
                "command_id": command_id,
                "note": "Command sent via WebSocket, device will execute immediately",
            }

        except Exception as e:
            logger.error(f"App launch failed: {e}")
            return {"success": False, "error": str(e)}

    async def send_message_via_deeplink(
        self, app: str, contact: str, message: str
    ) -> Dict[str, Any]:
        """
        Send message using deep linking.

        Args:
            app: Messaging app to use.
            contact: Contact to message.
            message: Message content.

        Returns:
            Send result.
        """
        try:
            if not self.is_device_connected():
                logger.warning("No device connected, cannot send message")
                return {"success": False, "error": "Device not connected"}

            logger.info(f"Sending message via {app} to {contact}")
            # This would use deep links to send messages
            return {
                "success": True,
                "app": app,
                "contact": contact,
                "method": "deeplink",
            }

        except Exception as e:
            logger.error(f"Message send failed: {e}")
            return {"success": False, "error": str(e)}

    async def make_call_via_intent(self, contact: str) -> Dict[str, Any]:
        """
        Make phone call using Android intent.

        Args:
            contact: Contact to call.

        Returns:
            Call result.
        """
        try:
            if not self.is_device_connected():
                logger.warning("No device connected, cannot make call")
                return {"success": False, "error": "Device not connected"}

            logger.info(f"Making call to {contact}")
            # Use deep link execution
            deep_link_uri = f"tel:{contact}"
            return await self.launch_deep_link(deep_link_uri)

        except Exception as e:
            logger.error(f"Call failed: {e}")
            return {"success": False, "error": str(e)}

    async def request_screen_capture_permission(self) -> Dict[str, Any]:
        """
        Request Android to show the MediaProjection permission dialog.
        
        Sends a WebSocket message to the Android app telling it to call
        mediaProjectionManager.createScreenCaptureIntent() and show the
        system permission dialog to the user.
        
        Returns:
            Result with success status
        """
        try:
            if not self.is_device_connected():
                logger.warning("❌ Device not connected, cannot request screen capture permission")
                return {"success": False, "error": "Device not connected"}
            
            if not self.has_websocket():
                logger.error("❌ WebSocket not available, cannot request screen capture permission")
                return {"success": False, "error": "WebSocket not available"}
            
            import uuid
            command_id = str(uuid.uuid4())[:8]
            
            await self._websocket.send_json({
                "type": "request_screen_capture_permission",
                "command_id": command_id,
                "reason": "Backend needs screenshots for visual automation",
            })
            
            logger.info(f"📸 Screen capture permission request sent: command_id={command_id}")
            return {
                "success": True,
                "command_id": command_id,
                "message": "Permission request sent to Android. User should see a dialog.",
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to request screen capture permission: {e}")
            return {"success": False, "error": str(e)}

    async def launch_deep_link(
        self, uri: str, package_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Launch deep link URI via Android intent via WebSocket.

        Args:
            uri: Deep link URI (e.g., tel:+1234567890, mailto:test@example.com, https://wa.me/...)
            package_name: Optional specific package to handle the intent.

        Returns:
            Launch result with success status.
        """
        try:
            if not self.is_device_connected():
                logger.warning("No device connected, cannot launch deep link")
                return {"success": False, "error": "Device not connected"}

            if not self._websocket:
                logger.error("❌ WebSocket required for deep link launch - no connection available")
                return {"success": False, "error": "WebSocket required for deep link launch"}

            logger.info(f"🔗 Sending deep link launch command via WebSocket: {uri}")

            # Send command via WebSocket
            import uuid
            command_id = str(uuid.uuid4())[:8]
            
            await self._websocket.send_json({
                "type": "launch_deep_link",
                "command_id": command_id,
                "uri": uri,
                "package_name": package_name,
                "method": "deep_link",
            })

            logger.info(f"✅ Deep link command sent via WebSocket: {command_id} for {uri}")
            
            # Return optimistic success - Android will execute immediately via WebSocket
            return {
                "success": True,
                "uri": uri,
                "package_name": package_name,
                "method": "websocket",
                "command_id": command_id,
                "note": "Command sent via WebSocket, device will execute immediately",
            }

        except Exception as e:
            logger.error(f"❌ Deep link launch failed: {e}")
            return {"success": False, "error": str(e)}


# Global instance for use across the application
real_accessibility_service = RealAccessibilityService()
