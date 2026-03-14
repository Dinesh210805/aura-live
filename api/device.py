"""Device registration endpoint."""

import time
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status

from constants import API_VERSION
from middleware.auth import verify_api_key
from middleware.rate_limit import limiter
from models.requests import DeviceRegistration
from utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/device/status")
@limiter.limit("60/minute")
async def get_device_status(request: Request) -> Dict[str, Any]:
    """
    Get current device connection status with troubleshooting hints.

    Returns connection state, screenshot availability, UI elements, and actionable hints.
    """
    try:
        from services.real_accessibility import real_accessibility_service

        device_info = real_accessibility_service.device_info
        screenshot_data = real_accessibility_service.last_screenshot
        screenshot = screenshot_data.screenshot if screenshot_data else None
        ui_elements = real_accessibility_service.ui_elements

        is_connected = real_accessibility_service.is_device_connected()
        screenshot_available = screenshot is not None and len(screenshot) > 1000
        screenshot_size = len(screenshot) if screenshot else 0
        ui_count = len(ui_elements) if ui_elements else 0

        device_status_info = {
            "connected": is_connected,
            "device_name": device_info.get("device_name") if device_info else None,
            "android_version": (
                device_info.get("android_version") if device_info else None
            ),
            "screen_dimensions": (
                {
                    "width": device_info.get("screen_width", 0) if device_info else 0,
                    "height": device_info.get("screen_height", 0) if device_info else 0,
                }
                if device_info
                else None
            ),
            "screenshot_available": screenshot_available,
            "screenshot_size_bytes": screenshot_size,
            "ui_elements_count": ui_count,
            "last_update_timestamp": (
                device_info.get("connected_at") if device_info else None
            ),
            "capabilities": device_info.get("capabilities", []) if device_info else [],
        }

        # Add troubleshooting hints based on status
        hints = []
        if not is_connected:
            hints = [
                "1. Open AURA app on your Android device",
                "2. Enable Accessibility Service (Settings → Accessibility → AURA)",
                "3. Check backend URL in app Settings (should be your PC IP)",
                "4. Look for 'Device registered' confirmation message",
                "5. Check if backend server is reachable from device",
            ]
            device_status_info["issue"] = "device_not_connected"
        elif not screenshot_available:
            hints = [
                "1. Open AURA app → Settings",
                "2. Tap 'Request screen capture' button",
                "3. Grant permission when Android prompts",
                "4. Restart AURA app to activate permission",
                "5. Check if permission is enabled in Android Settings → Apps → AURA",
            ]
            device_status_info["issue"] = "screenshot_permission_missing"
        elif ui_count == 0:
            hints = [
                "1. Ensure accessibility service is enabled and active",
                "2. Try navigating to a different app",
                "3. Restart AURA app",
                "4. Check accessibility permissions in Android Settings",
            ]
            device_status_info["issue"] = "no_ui_elements"
        else:
            hints = ["✅ All systems operational"]
            device_status_info["issue"] = None

        device_status_info["troubleshooting_hints"] = hints

        logger.info(
            f"Device status check: connected={is_connected}, screenshot={screenshot_available}, ui_elements={ui_count}"
        )

        return device_status_info

    except Exception as e:
        logger.error(f"Error getting device status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get device status",
        )


@router.get("/device/ui-elements")
@limiter.limit("30/minute")
async def get_ui_elements(request: Request) -> Dict[str, Any]:
    """
    Get current screen UI elements via UITreeService.
    
    Requests fresh UI tree from Android and returns all elements with their properties.
    Used by debugging tools and external scripts.
    
    Returns:
        UI elements array with coordinates, text, flags, etc.
    """
    try:
        from services.real_accessibility import real_accessibility_service
        from services.ui_tree_service import get_ui_tree_service
        import uuid
        
        if not real_accessibility_service.is_device_connected():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Device not connected. Ensure Android app is running and WebSocket is connected.",
            )
        
        ui_tree_service = get_ui_tree_service()
        request_id = str(uuid.uuid4())[:8]
        
        logger.info(f"📋 UI elements request from API: request_id={request_id}")
        
        ui_tree = await ui_tree_service.request_ui_tree(
            request_id=request_id,
            reason="API request from external tool"
        )
        
        if not ui_tree or not ui_tree.elements:
            return {
                "success": False,
                "error": "Failed to get UI tree from device",
                "elements": [],
                "screen_width": real_accessibility_service.device_info.get("screen_width", 1080),
                "screen_height": real_accessibility_service.device_info.get("screen_height", 2400),
            }
        
        # Elements are already dicts from UITreePayload
        elements_data = ui_tree.elements
        
        return {
            "success": True,
            "elements": elements_data,
            "total_count": len(elements_data),
            "clickable_count": sum(1 for e in elements_data if e.get("clickable", e.get("isClickable", False))),
            "scrollable_count": sum(1 for e in elements_data if e.get("scrollable", e.get("isScrollable", False))),
            "editable_count": sum(1 for e in elements_data if e.get("editable", e.get("isEditable", False))),
            "screen_width": ui_tree.screen_width,
            "screen_height": ui_tree.screen_height,
            "current_app": elements_data[0].get("packageName", "Unknown") if elements_data else "Unknown",
            "timestamp": int(time.time() * 1000),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting UI elements: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get UI elements",
        )


@router.post("/device/request-screen-capture")
@limiter.limit("10/minute")
async def request_screen_capture(request: Request) -> Dict[str, Any]:
    """
    Request Android to show the screen capture permission dialog.
    
    Call this endpoint when screenshots are returning empty (0 bytes).
    The Android app will show the MediaProjection permission prompt.
    
    Returns:
        Status of the permission request
    """
    try:
        from services.real_accessibility import real_accessibility_service
        
        if not real_accessibility_service.is_device_connected():
            return {
                "success": False,
                "error": "Device not connected",
                "hint": "Connect the Android device first via WebSocket",
            }
        
        result = await real_accessibility_service.request_screen_capture_permission()
        
        if result.get("success"):
            return {
                "success": True,
                "message": "Screen capture permission request sent to Android",
                "next_steps": [
                    "1. Look at your Android device",
                    "2. Tap 'Start now' or 'Allow' on the permission dialog",
                    "3. Try your command again - screenshots should work",
                ],
            }
        else:
            return result
            
    except Exception as e:
        logger.error(f"Error requesting screen capture: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to request screen capture",
        )


@router.post("/device/register")
@limiter.limit("10/minute")
async def register_device(
    device_info: DeviceRegistration,
    request: Request,
    api_key: str = Depends(verify_api_key),
) -> Dict[str, Any]:
    """
    Register device with API key authentication.

    Args:
        device_info: Device registration data
        request: FastAPI request
        api_key: Validated API key

    Returns:
        Registration confirmation
    """
    try:
        logger.info(
            f"📱 Device registration: {device_info.device_name} [Request: {request.state.request_id}]"
        )

        if not device_info.device_name or len(device_info.device_name.strip()) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Device name is required",
            )

        if device_info.screen_width <= 0 or device_info.screen_height <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Valid screen dimensions required",
            )

        from services.real_accessibility import real_accessibility_service

        device_data = {
            "device_name": device_info.device_name,
            "android_version": device_info.android_version,
            "screen_width": device_info.screen_width,
            "screen_height": device_info.screen_height,
            "density_dpi": device_info.density_dpi,
            "app_version": device_info.app_version,
            "capabilities": device_info.capabilities,
            "connected_at": time.time(),
            "registration_timestamp": int(time.time() * 1000),
        }

        real_accessibility_service.set_device_connection(device_data)
        logger.info(f" Device registered: {device_info.device_name}")

        return {
            "status": "registered",
            "device_id": device_info.device_name,
            "message": f"Device {device_info.device_name} registered successfully",
            "registration_details": {
                "timestamp": int(time.time() * 1000),
                "server_version": "1.0.0",
                "api_version": API_VERSION,
            },
            "supported_endpoints": [
                f"/api/{API_VERSION}/device/ui-data",
                f"/api/{API_VERSION}/device/execute-gesture",
                f"/api/{API_VERSION}/tasks/execute",
            ],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"❌ Device registration failed: {e} [Request: {request.state.request_id}]"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Device registration failed: {str(e)}",
        )
