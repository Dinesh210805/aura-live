"""
Real Accessibility API Endpoints.

Handles communication between Android AccessibilityService and AURA backend.
Provides endpoints for screenshot capture, UI analysis, and gesture execution.
"""

import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.real_accessibility import real_accessibility_service
from services.screenshot_service import get_screenshot_service
from utils.logger import get_logger

logger = get_logger(__name__)

# Create router with both /accessibility (legacy) and /api/v1/accessibility (new) support
router = APIRouter(tags=["Real Accessibility"])


class DeviceConnectionRequest(BaseModel):
    """Device connection information."""

    screen_width: int = Field(..., description="Screen width in pixels")
    screen_height: int = Field(..., description="Screen height in pixels")
    density_dpi: int = Field(..., description="Screen density DPI")
    device_name: str = Field(..., description="Device name/model")
    android_version: str = Field(..., description="Android version")


class UIDataRequest(BaseModel):
    """UI data from Android AccessibilityService."""

    screenshot: str = Field(..., description="Base64 encoded screenshot")
    screen_width: int = Field(..., description="Screen width in pixels")
    screen_height: int = Field(..., description="Screen height in pixels")
    timestamp: int = Field(..., description="Timestamp of capture")
    ui_elements: List[Dict[str, Any]] = Field(..., description="UI elements array")


class GestureExecutionRequest(BaseModel):
    """Gesture execution request."""

    action: str = Field(..., description="Gesture action (tap, swipe, long_press)")
    x: Optional[int] = Field(None, description="X coordinate")
    y: Optional[int] = Field(None, description="Y coordinate")
    x2: Optional[int] = Field(None, description="Second X coordinate for swipe")
    y2: Optional[int] = Field(None, description="Second Y coordinate for swipe")
    duration: int = Field(300, description="Gesture duration in milliseconds")


class UIAnalysisResponse(BaseModel):
    """UI analysis response."""

    elements_found: int
    clickable_elements: int
    editable_elements: int
    scrollable_elements: int
    screen_info: Dict[str, int]
    elements: List[Dict[str, Any]]


@router.post("/connect")
async def connect_device(connection_data: DeviceConnectionRequest):
    """
    Register device connection with accessibility service.

    Called by Android app when accessibility service starts.
    """
    try:
        device_info = {
            "screen_width": connection_data.screen_width,
            "screen_height": connection_data.screen_height,
            "density_dpi": connection_data.density_dpi,
            "device_name": connection_data.device_name,
            "android_version": connection_data.android_version,
            "connected_at": time.time(),
        }

        real_accessibility_service.set_device_connection(device_info)

        logger.info(f"Device connected: {connection_data.device_name}")

        return {
            "status": "connected",
            "message": "Device registered successfully",
            "backend_ready": True,
            "device_id": f"{connection_data.device_name}_{int(time.time())}",
        }

    except Exception as e:
        logger.error(f"Failed to connect device: {e}")
        raise HTTPException(status_code=500, detail="Device connection failed")


@router.post("/ui-data")
async def receive_ui_data(ui_data: UIDataRequest):
    """
    Receive UI data from Android AccessibilityService.

    This endpoint handles the smart hybrid approach:
    - Always receives UI hierarchy data (lightweight)
    - Optionally receives screenshot data (when needed)
    - Processes and stores both types efficiently
    """
    try:
        # Convert request to internal format
        ui_data_dict = {
            "screenshot": ui_data.screenshot,
            "screen_width": ui_data.screen_width,
            "screen_height": ui_data.screen_height,
            "timestamp": ui_data.timestamp,
            "ui_elements": ui_data.ui_elements,
            "has_screenshot": bool(ui_data.screenshot.strip()),
            "capture_reason": "android_update",
        }

        # Update the accessibility service with new data
        success = real_accessibility_service.update_ui_data(ui_data_dict)

        if success:
            elements_count = len(ui_data.ui_elements) if ui_data.ui_elements else 0
            has_screenshot = bool(ui_data.screenshot.strip())

            logger.info(
                f"📱 UI data received: {elements_count} elements, screenshot: {has_screenshot}"
            )

            return {
                "status": "success",
                "message": "UI data processed successfully",
                "elements_received": elements_count,
                "screenshot_received": has_screenshot,
                "timestamp": ui_data.timestamp,
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to process UI data")

    except Exception as e:
        logger.error(f"❌ Failed to process UI data: {e}")
        raise HTTPException(
            status_code=500, detail="UI data processing failed"
        )


@router.get("/current-ui")
async def get_current_ui() -> UIAnalysisResponse:
    """
    Get current UI analysis data.

    Returns the most recent UI hierarchy and screenshot data.
    """
    try:
        if not real_accessibility_service.last_screenshot:
            # Trigger fresh UI capture if no data available
            await real_accessibility_service.analyze_real_ui()  # Result ignored, just triggers capture

        screenshot_data = real_accessibility_service.last_screenshot
        if not screenshot_data:
            raise HTTPException(status_code=404, detail="No UI data available")

        elements = screenshot_data.uiElements
        clickable_count = sum(1 for elem in elements if elem.isClickable)
        editable_count = sum(1 for elem in elements if elem.isEditable)
        scrollable_count = sum(1 for elem in elements if elem.isScrollable)

        screen_info = await real_accessibility_service.get_screen_info()

        # Convert elements to dict format for JSON response
        elements_data = []
        for elem in elements:
            elem_dict = {
                "id": elem.id,
                "className": elem.className,
                "text": elem.text,
                "contentDescription": elem.contentDescription,
                "bounds": elem.bounds,
                "isClickable": elem.isClickable,
                "isScrollable": elem.isScrollable,
                "isEditable": elem.isEditable,
                "isEnabled": elem.isEnabled,
                "packageName": elem.packageName,
                "viewId": elem.viewId,
            }
            elements_data.append(elem_dict)

        return UIAnalysisResponse(
            elements_found=len(elements),
            clickable_elements=clickable_count,
            editable_elements=editable_count,
            scrollable_elements=scrollable_count,
            screen_info=screen_info,
            elements=elements_data,
        )

    except Exception as e:
        logger.error(f"Failed to get current UI: {e}")
        raise HTTPException(status_code=500, detail="UI analysis failed")


@router.post("/execute-gesture")
async def execute_gesture(gesture_request: GestureExecutionRequest):
    """
    Execute gesture on connected Android device.

    Sends gesture command to Android AccessibilityService for execution.
    """
    try:
        # Validate gesture parameters
        if gesture_request.action in ["tap", "click"] and (
            gesture_request.x is None or gesture_request.y is None
        ):
            raise HTTPException(
                status_code=400, detail="Tap gesture requires x and y coordinates"
            )

        if gesture_request.action == "swipe" and any(
            coord is None
            for coord in [
                gesture_request.x,
                gesture_request.y,
                gesture_request.x2,
                gesture_request.y2,
            ]
        ):
            raise HTTPException(
                status_code=400,
                detail="Swipe gesture requires x, y, x2, y2 coordinates",
            )

        # Execute the gesture
        success = await real_accessibility_service.execute_real_gesture(
            action=gesture_request.action,
            x=gesture_request.x,
            y=gesture_request.y,
            x2=gesture_request.x2,
            y2=gesture_request.y2,
            duration=gesture_request.duration,
        )

        if success:
            logger.info(f"Gesture executed successfully: {gesture_request.action}")
            return {
                "status": "executed",
                "action": gesture_request.action,
                "success": True,
                "timestamp": time.time(),
            }
        else:
            raise HTTPException(status_code=500, detail="Gesture execution failed")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Gesture execution error: {e}")
        raise HTTPException(
            status_code=500, detail="Gesture execution failed"
        )


@router.get("/screenshot")
async def get_current_screenshot():
    """
    Get current device screenshot.

    Returns base64 encoded screenshot from the most recent capture.
    If no screenshot is cached, requests one from the device.
    """
    try:
        if real_accessibility_service.last_screenshot:
            return {
                "screenshot": real_accessibility_service.last_screenshot.screenshot,
                "width": real_accessibility_service.last_screenshot.screenWidth,
                "height": real_accessibility_service.last_screenshot.screenHeight,
                "timestamp": real_accessibility_service.last_screenshot.timestamp,
                "format": "base64_png",
            }
        else:
            # Request a fresh screenshot from the device
            logger.info("No cached screenshot, requesting from device...")
            screenshot_service = get_screenshot_service()
            request_id = str(uuid.uuid4())
            result = await screenshot_service.request_screenshot(request_id, "api_request")
            
            if result and result.screenshot_base64:
                return {
                    "screenshot": result.screenshot_base64,
                    "width": result.screen_width,
                    "height": result.screen_height,
                    "timestamp": result.timestamp,
                    "format": "base64_png",
                }
            else:
                raise HTTPException(
                    status_code=404, 
                    detail="Screenshot not available. Device may not have MediaProjection permission."
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Screenshot retrieval failed: {e}")
        raise HTTPException(status_code=500, detail="Screenshot capture failed")


@router.post("/find-element")
async def find_element(request: Dict[str, Any]):
    """
    Find UI element by various criteria.

    Supports finding elements by text, content description, class name, etc.
    """
    try:
        search_text = request.get("text")
        search_class = request.get("className")
        search_description = request.get("contentDescription")

        if not any([search_text, search_class, search_description]):
            raise HTTPException(status_code=400, detail="Search criteria required")

        elements, _ = await real_accessibility_service.analyze_real_ui()  # Unpack tuple
        matching_elements = []

        for element in elements:
            match = False

            if search_text and element.text:
                if search_text.lower() in element.text.lower():
                    match = True

            if search_class and element.className:
                if search_class.lower() in element.className.lower():
                    match = True

            if search_description and element.contentDescription:
                if search_description.lower() in element.contentDescription.lower():
                    match = True

            if match:
                elem_dict = {
                    "id": element.id,
                    "className": element.className,
                    "text": element.text,
                    "contentDescription": element.contentDescription,
                    "bounds": element.bounds,
                    "isClickable": element.isClickable,
                    "centerCoordinates": [
                        element.bounds["centerX"],
                        element.bounds["centerY"],
                    ],
                }
                matching_elements.append(elem_dict)

        return {
            "found": len(matching_elements),
            "elements": matching_elements,
            "search_criteria": request,
        }

    except Exception as e:
        logger.error(f"Element search failed: {e}")
        raise HTTPException(status_code=500, detail="Element search failed")


@router.get("/device-info")
async def get_device_info():
    """
    Get connected device information.
    """
    try:
        return {
            "device_info": real_accessibility_service.device_info,
            "service_status": (
                "connected"
                if real_accessibility_service.device_info["connected"]
                else "disconnected"
            ),
            "last_activity": time.time(),
        }

    except Exception as e:
        logger.error(f"Failed to get device info: {e}")
        raise HTTPException(status_code=500, detail="Device info retrieval failed")
