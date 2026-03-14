"""
UI Tree Service - Retrieves UI hierarchy from Android.

Implements the UI Tree Reconstruction contract from the blueprint.
"""

import asyncio
import time
from typing import Dict, List, Optional, Tuple

from perception.models import UITreePayload
from services.real_accessibility import real_accessibility_service
from utils.logger import get_logger

logger = get_logger(__name__)


class UITreeService:
    """
    Service for retrieving UI tree from Android device.

    Implements pull-based retrieval - Android never pushes UI data autonomously.
    """

    def __init__(self):
        """Initialize UI Tree Service."""
        self.last_request_id: Optional[str] = None
        self.pending_requests: Dict[str, asyncio.Future] = {}
        self.last_validation_failure: Optional[Dict] = None  # Track Android validation failures

    async def request_ui_tree(
        self, request_id: str, reason: str
    ) -> Optional[UITreePayload]:
        """
        Request UI tree from Android device via WebSocket.

        Backend → Android (WebSocket):
        REQUEST_UI_TREE { request_id, reason }

        Android must:
        - Traverse AccessibilityNodeInfo
        - Extract minimal deterministic fields only:
          - text
          - contentDescription
          - boundsInScreen
          - className
          - clickable / scrollable
          - resourceId (if present)
        - Attach screen metadata + timestamp

        Args:
            request_id: Unique request identifier
            reason: Reason for requesting UI tree

        Returns:
            UITreePayload or None if request failed/timed out
        """
        try:
            if not real_accessibility_service.is_device_connected():
                logger.warning("❌ Device not connected, cannot request UI tree")
                return None

            if not real_accessibility_service.has_websocket():
                logger.error("❌ WebSocket not available, cannot request UI tree")
                return None

            logger.info(f"📋 Requesting UI tree: request_id={request_id}, reason={reason}")

            # Create future to wait for response
            future = asyncio.get_running_loop().create_future()
            self.pending_requests[request_id] = future

            # Send request via WebSocket
            websocket = real_accessibility_service._websocket
            await websocket.send_json({
                "type": "request_ui_tree",
                "request_id": request_id,
                "reason": reason,
            })

            # Wait for response with timeout.
            # 15s is needed because apps can take 10-15s to fully render after launch.
            try:
                ui_tree_data = await asyncio.wait_for(future, timeout=15.0)
                logger.info(f"✅ UI tree received: request_id={request_id}")
                return self._parse_ui_tree_response(ui_tree_data)
            except asyncio.TimeoutError:
                logger.warning(f"⏱️ UI tree request timed out: request_id={request_id}")
                return None
            finally:
                self.pending_requests.pop(request_id, None)

        except Exception as e:
            logger.error(f"❌ Failed to request UI tree: {e}")
            self.pending_requests.pop(request_id, None)
            return None

    def handle_ui_tree_response(self, request_id: str, ui_tree_data: Dict) -> bool:
        """
        Handle incoming UI tree response from Android.

        Called by WebSocket router when ui_tree_response message is received.
        Also syncs screen dimensions to device_info for accurate gesture validation.

        Args:
            request_id: Request ID that this response corresponds to
            ui_tree_data: UI tree data from Android

        Returns:
            True if response was handled, False if no pending request
        """
        logger.info(f"📥 Received UI tree response: request_id={request_id}, pending={list(self.pending_requests.keys())}")
        
        # CRITICAL: Sync screen dimensions from UI tree to device_info
        # This ensures gesture coordinate validation uses accurate screen bounds
        screen_width = ui_tree_data.get("screen_width", ui_tree_data.get("screenWidth"))
        screen_height = ui_tree_data.get("screen_height", ui_tree_data.get("screenHeight"))
        
        if screen_width and screen_height:
            current_width = real_accessibility_service.device_info.get("screen_width", 0)
            current_height = real_accessibility_service.device_info.get("screen_height", 0)
            
            if screen_width != current_width or screen_height != current_height:
                logger.info(f"📱 Updating device_info screen size: {current_width}x{current_height} → {screen_width}x{screen_height}")
                real_accessibility_service.device_info["screen_width"] = screen_width
                real_accessibility_service.device_info["screen_height"] = screen_height
        
        if request_id in self.pending_requests:
            future = self.pending_requests[request_id]
            if not future.done():
                logger.info(f"✅ Matched pending request {request_id}, setting result with {len(ui_tree_data.get('elements', []))} elements")
                future.set_result(ui_tree_data)
                return True
            else:
                logger.warning(f"⚠️ Future for {request_id} already done")
        else:
            logger.warning(f"⚠️ No pending request for {request_id}")
        return False

    def _parse_ui_tree_response(self, data: Dict) -> Optional[UITreePayload]:
        """
        Parse UI tree response from Android into UITreePayload.

        Handles validation failures from Android (when validation_failed=true).

        Args:
            data: Raw UI tree data from Android

        Returns:
            Parsed UITreePayload or None if parsing failed or validation failed
        """
        try:
            # Check if Android rejected the UI tree
            if data.get("validation_failed", False):
                reason = data.get("validation_reason", "Unknown validation failure")
                app_category = data.get("app_category", "unknown")
                requires_vision = data.get("requires_vision", False)
                
                log = logger.info if requires_vision else logger.warning
                log(
                    f"📱 Android UI tree skipped: {reason}, "
                    f"app_category={app_category}, requires_vision={requires_vision}"
                )
                
                # Store metadata for modality escalation
                self.last_validation_failure = {
                    "reason": reason,
                    "app_category": app_category,
                    "requires_vision": requires_vision,
                    "timestamp": data.get("timestamp", int(time.time() * 1000)),
                }
                return None
            
            elements = data.get("elements", [])
            screen_width = data.get("screen_width", data.get("screenWidth", 1080))
            screen_height = data.get("screen_height", data.get("screenHeight", 1920))
            orientation = data.get("orientation", "portrait")
            timestamp = data.get("timestamp", int(time.time() * 1000))
            root_node_id = data.get("root_node_id")
            package_name = data.get("package_name")

            # Extract deterministic fields from elements
            processed_elements = []
            for i, elem in enumerate(elements):
                class_name = elem.get("className", elem.get("class_name", ""))
                processed_elem = {
                    "text": elem.get("text", ""),
                    "contentDescription": elem.get("contentDescription", elem.get("content_description", "")),
                    "bounds": elem.get("bounds", elem.get("boundsInScreen", {})),
                    "className": class_name,
                    "clickable": elem.get("clickable", elem.get("isClickable", False)),
                    "scrollable": elem.get("scrollable", elem.get("isScrollable", False)),
                    "editable": elem.get("editable", elem.get("isEditable", False)),
                    "focused": elem.get("focused", elem.get("isFocused", False)),
                    "actions": elem.get("actions", []),
                    "resourceId": elem.get("resourceId", elem.get("viewId", elem.get("viewIdResourceName", ""))),
                }
                # Add package_name to first element for app identification
                if i == 0 and package_name:
                    processed_elem["packageName"] = package_name
                processed_elements.append(processed_elem)

            # Sanitize sensitive data from UI tree
            try:
                from perception.sanitizer import sanitize_ui_tree
                processed_elements = sanitize_ui_tree(processed_elements, package_name)
            except Exception as sanitize_error:
                logger.warning(f"Sanitization failed: {sanitize_error}")

            # Clear any previous validation failure
            self.last_validation_failure = None
            
            return UITreePayload(
                elements=processed_elements,
                screen_width=screen_width,
                screen_height=screen_height,
                orientation=orientation,
                timestamp=timestamp,
                root_node_id=root_node_id,
            )

        except Exception as e:
            logger.error(f"❌ Failed to parse UI tree response: {e}")
            return None


# Global instance
ui_tree_service = UITreeService()


def get_ui_tree_service() -> UITreeService:
    """Get the global UI tree service instance."""
    return ui_tree_service
