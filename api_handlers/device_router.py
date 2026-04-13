"""
Device management router for AURA backend.

Handles device registration, UI data upload, and gesture execution.
"""

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator

from utils.logger import get_logger

logger = get_logger(__name__)

# Router with /device prefix for device management endpoints
router = APIRouter(prefix="/device", tags=["Device Management"])

# App inventory file path
APP_INVENTORY_FILE = Path("device_app_inventory.json")


class AppInfo(BaseModel):
    """Installed app information."""

    package_name: str = Field(..., description="Package name")
    app_name: str = Field(..., description="Human-readable app name")
    is_system_app: bool = Field(default=False, description="Is system app")
    version_name: str = Field(default="", description="App version")
    deep_links: List[str] = Field(
        default_factory=list, description="Supported deep link schemes"
    )
    intent_filters: List[Dict[str, Any]] = Field(
        default_factory=list, description="Intent filter actions"
    )


class DeviceRegistration(BaseModel):
    """Device registration request model."""

    device_name: str = Field(
        ..., min_length=1, max_length=100, description="Device name/identifier"
    )
    android_version: str = Field(..., description="Android OS version")
    screen_width: int = Field(..., gt=0, le=4096, description="Screen width in pixels")
    screen_height: int = Field(
        ..., gt=0, le=4096, description="Screen height in pixels"
    )
    density_dpi: int = Field(
        default=420, gt=0, le=640, description="Screen density DPI"
    )
    app_version: str = Field(default="1.0.0", description="AURA app version")
    capabilities: List[str] = Field(
        default_factory=list, description="Device capabilities"
    )
    installed_apps: List[AppInfo] = Field(
        default_factory=list, description="Installed apps inventory"
    )

    @field_validator("device_name")
    @classmethod
    def validate_device_name(cls, v):
        """Validate device name."""
        if not v or not v.strip():
            raise ValueError("Device name cannot be empty")
        return v.strip()


class DeviceUIData(BaseModel):
    """UI data upload from device."""

    screenshot: str = Field(..., description="Base64 encoded screenshot")
    ui_elements: List[Dict[str, Any]] = Field(..., description="UI element hierarchy")
    screen_width: int = Field(..., gt=0, description="Screen width in pixels")
    screen_height: int = Field(..., gt=0, description="Screen height in pixels")
    timestamp: int = Field(..., description="Capture timestamp")
    package_name: str = Field(default="", description="Current app package name")
    activity_name: str = Field(default="", description="Current activity name")
    capture_reason: str = Field(default="manual", description="Reason for capture")

    @field_validator("screenshot")
    @classmethod
    def validate_screenshot(cls, v):
        """Validate screenshot data."""
        if len(v) > 5 * 1024 * 1024:  # 5MB base64 limit
            raise ValueError("Screenshot data too large (max 5MB)")
        return v

    @field_validator("ui_elements")
    @classmethod
    def validate_ui_elements(cls, v):
        """Validate UI elements."""
        if len(v) > 10000:  # Reasonable limit
            raise ValueError("Too many UI elements (max 10000)")
        return v


class GestureRequest(BaseModel):
    """Gesture execution request."""

    action: str = Field(..., description="Gesture action type")
    x: Optional[int] = Field(None, ge=0, description="X coordinate")
    y: Optional[int] = Field(None, ge=0, description="Y coordinate")
    x2: Optional[int] = Field(None, ge=0, description="Second X coordinate for swipe")
    y2: Optional[int] = Field(None, ge=0, description="Second Y coordinate for swipe")
    duration: int = Field(
        default=300, ge=0, le=5000, description="Gesture duration in ms"
    )

    @field_validator("action")
    @classmethod
    def validate_action(cls, v):
        """Validate action type."""
        valid_actions = ["tap", "long_press", "swipe", "scroll", "back", "home"]
        if v.lower() not in valid_actions:
            raise ValueError(f"Action must be one of: {', '.join(valid_actions)}")
        return v.lower()


@router.post("/register")
async def register_device(
    device_info: DeviceRegistration, request: Request
) -> Dict[str, Any]:
    """
    Register a new Android device with the backend.

    Args:
        device_info: Device registration information
        request: FastAPI request object

    Returns:
        Registration confirmation with device ID
    """
    try:
        request_id = getattr(request.state, "request_id", "unknown")
        logger.info(
            f"📱 Device registration: {device_info.device_name} [Request: {request_id}]"
        )

        # Get accessibility service
        from services.real_accessibility import real_accessibility_service

        accessibility_service = real_accessibility_service

        # Register device
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

        accessibility_service.set_device_connection(device_data)

        # Store app inventory if provided
        if device_info.installed_apps:
            _store_app_inventory(device_info.device_name, device_info.installed_apps)
            logger.info(
                f"📦 Stored inventory: {len(device_info.installed_apps)} apps for {device_info.device_name}"
            )

        logger.info(f"✅ Device registered: {device_info.device_name}")

        return {
            "status": "registered",
            "device_id": device_info.device_name,
            "message": f"Device {device_info.device_name} registered successfully",
            "registration_details": {
                "timestamp": int(time.time() * 1000),
                "server_version": "1.0.0",
            },
        }

    except Exception as e:
        logger.error(f"❌ Device registration failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Device registration failed: {str(e)}",
        )


@router.post("/ui-data")
async def upload_ui_data(ui_data: DeviceUIData, request: Request) -> Dict[str, Any]:
    """
    Upload UI hierarchy and screenshot data from Android device.

    Args:
        ui_data: UI data including screenshot and element hierarchy
        request: FastAPI request object

    Returns:
        Upload confirmation
    """
    try:
        # Determine mode and log it
        has_screenshot = bool(ui_data.screenshot and len(ui_data.screenshot) > 100)
        screenshot_size_kb = len(ui_data.screenshot) / 1024 if ui_data.screenshot else 0
        mode_indicator = (
            "📸 FULL MODE (UI + Screenshot)" if has_screenshot else "📋 UI-ONLY MODE"
        )

        logger.info(
            f"📥 UI Data Received | {mode_indicator} | Elements: {len(ui_data.ui_elements)} | "
            f"Screenshot: {screenshot_size_kb:.1f}KB | App: {ui_data.package_name}"
        )

        # Get accessibility service
        from services.real_accessibility import real_accessibility_service

        accessibility_service = real_accessibility_service

        # Convert to format expected by service
        ui_data_dict = {
            "screenshot": ui_data.screenshot,
            "ui_elements": ui_data.ui_elements,
            "screen_width": ui_data.screen_width,
            "screen_height": ui_data.screen_height,
            "timestamp": ui_data.timestamp,
            "package_name": ui_data.package_name,
            "activity_name": ui_data.activity_name,
            "capture_reason": ui_data.capture_reason,
            "has_screenshot": has_screenshot,
        }

        # Update service
        success = accessibility_service.update_ui_data(ui_data_dict)

        if success:
            logger.info(f"✅ UI data stored | {mode_indicator} | Ready for analysis")
            return {
                "status": "success",
                "message": "UI data updated successfully",
                "elements_processed": len(ui_data.ui_elements),
                "timestamp": ui_data.timestamp,
                "has_screenshot": has_screenshot,
                "mode": "full" if has_screenshot else "ui_only",
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Device not registered or not connected",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ UI data upload failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"UI data upload failed: {str(e)}",
        )


@router.post("/execute-gesture")
async def execute_gesture(gesture: GestureRequest, request: Request) -> Dict[str, Any]:
    """
    Execute a gesture on the connected Android device.

    Args:
        gesture: Gesture execution request
        request: FastAPI request object

    Returns:
        Execution result
    """
    try:
        logger.info(f"👆 Gesture execution: {gesture.action}")

        # Get accessibility service
        from services.real_accessibility import real_accessibility_service

        accessibility_service = real_accessibility_service

        if not accessibility_service.is_device_connected():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="No device connected"
            )

        # Convert to gesture format
        gesture_data = {
            "action": gesture.action,
            "x": gesture.x,
            "y": gesture.y,
            "x2": gesture.x2,
            "y2": gesture.y2,
            "duration": gesture.duration,
        }

        # Execute gesture
        result = await accessibility_service.dispatch_gesture(gesture_data)

        logger.info(f"✅ Gesture executed: {gesture.action}")
        return {
            "status": "executed",
            "action": gesture.action,
            "result": result,
            "timestamp": int(time.time() * 1000),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Gesture execution failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gesture execution failed: {str(e)}",
        )


@router.get("/status")
async def get_device_status(request: Request) -> Dict[str, Any]:
    """
    Get current device connection status.

    Args:
        request: FastAPI request object

    Returns:
        Device status information
    """
    try:
        from services.real_accessibility import real_accessibility_service

        accessibility_service = real_accessibility_service

        is_connected = accessibility_service.is_device_connected()
        device_info = accessibility_service.device_info

        return {
            "connected": is_connected,
            "device_name": accessibility_service.connected_device,
            "device_info": device_info,
            "screen_width": (
                device_info.get("screen_width", 1080) if device_info else 1080
            ),
            "screen_height": (
                device_info.get("screen_height", 1920) if device_info else 1920
            ),
            "last_screenshot": accessibility_service.last_screenshot is not None,
            "ui_elements_available": accessibility_service.last_ui_analysis is not None,
        }

    except Exception as e:
        logger.error(f"❌ Device status check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Device status check failed: {str(e)}",
        )


@router.get("/ui-tree")
async def get_ui_tree(request: Request) -> Dict[str, Any]:
    """
    Get the raw unfiltered accessibility UI tree from the connected device.

    Unlike /ui-snapshot (cached) or perceive_screen (full perception pipeline),
    this sends a live request_ui_tree WebSocket message to the device and returns
    the full element tree with all fields including resourceId, hierarchy, and actions.

    Returns 422 with validation_failed=true for apps that block accessibility
    (games, media players with DRM).
    """
    try:
        from services.real_accessibility import real_accessibility_service
        from services.ui_tree_service import get_ui_tree_service

        if not real_accessibility_service.is_device_connected():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No device connected",
            )

        ui_tree_service = get_ui_tree_service()
        request_id = str(uuid.uuid4())
        payload = await ui_tree_service.request_ui_tree(request_id, reason="mcp_api")

        if payload is None:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="UI tree request timed out — device did not respond within 15s",
            )

        elements_out = []
        for elem in payload.elements:
            elements_out.append(
                {
                    "nodeId": elem.nodeId if hasattr(elem, "nodeId") else None,
                    "resourceId": elem.resourceId if hasattr(elem, "resourceId") else None,
                    "className": elem.className,
                    "text": elem.text,
                    "contentDescription": elem.contentDescription,
                    "bounds": elem.bounds if hasattr(elem, "bounds") else None,
                    "clickable": elem.clickable if hasattr(elem, "clickable") else False,
                    "scrollable": elem.scrollable if hasattr(elem, "scrollable") else False,
                    "editable": elem.editable if hasattr(elem, "editable") else False,
                    "focused": elem.focused if hasattr(elem, "focused") else False,
                    "enabled": elem.enabled if hasattr(elem, "enabled") else True,
                    "actions": elem.actions if hasattr(elem, "actions") else [],
                    "packageName": elem.packageName if hasattr(elem, "packageName") else None,
                }
            )

        return {
            "status": "success",
            "validation_failed": False,
            "elements": elements_out,
            "element_count": len(elements_out),
            "screen_width": payload.screen_width,
            "screen_height": payload.screen_height,
            "orientation": payload.orientation,
            "timestamp": payload.timestamp,
        }

    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        if "validation_failed" in error_msg.lower() or "accessibility" in error_msg.lower():
            return {
                "status": "validation_failed",
                "validation_failed": True,
                "message": "App blocks accessibility tree access (game/DRM/media). Use get_screenshot() instead.",
                "elements": [],
                "element_count": 0,
            }
        logger.error(f"❌ UI tree fetch failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"UI tree fetch failed: {str(e)}",
        )


@router.get("/ui-snapshot")
async def get_ui_snapshot(request: Request) -> Dict[str, Any]:
    """
    Get current UI snapshot (screenshot + elements) from connected device.

    Returns the last captured UI data including screenshot and element hierarchy.
    """
    try:
        from services.real_accessibility import real_accessibility_service

        accessibility_service = real_accessibility_service

        if not accessibility_service.is_device_connected():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="No device connected"
            )

        # Get screenshot data (contains both screenshot and UI elements)
        screenshot_data = accessibility_service.last_screenshot
        screenshot_b64 = ""
        ui_elements = []

        if screenshot_data:
            # Screenshot is already base64 string
            if screenshot_data.screenshot:
                screenshot_b64 = screenshot_data.screenshot

            # UI elements are in screenshot_data.uiElements
            if screenshot_data.uiElements:
                for elem in screenshot_data.uiElements:
                    ui_elements.append(
                        {
                            "nodeId": elem.nodeId,
                            "className": elem.className,
                            "text": elem.text,
                            "contentDescription": elem.contentDescription,
                            "centerX": elem.centerX,
                            "centerY": elem.centerY,
                            "left": elem.left,
                            "top": elem.top,
                            "right": elem.right,
                            "bottom": elem.bottom,
                            "clickable": elem.clickable,
                            "enabled": elem.enabled,
                            "visible": elem.visible,
                        }
                    )

        device_info = accessibility_service.device_info or {}

        return {
            "status": "success",
            "screenshot": screenshot_b64,
            "elements": ui_elements,
            "screen_width": device_info.get("screen_width", 1080),
            "screen_height": device_info.get("screen_height", 1920),
            "element_count": len(ui_elements),
            "has_screenshot": len(screenshot_b64) > 100,
            "timestamp": int(time.time() * 1000),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ UI snapshot failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"UI snapshot failed: {str(e)}",
        )


@router.post("/request-ui")
async def request_ui_capture(request: Request) -> Dict[str, Any]:
    """
    Request fresh UI capture from the connected device.

    Sends WebSocket message to device to capture UI data + screenshot.
    """
    try:
        from services.real_accessibility import real_accessibility_service

        accessibility_service = real_accessibility_service

        if not accessibility_service.is_device_connected():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="No device connected"
            )

        # Use WebSocket to request UI (faster and more reliable)
        success = await accessibility_service.request_fresh_screenshot()

        if success:
            logger.info("📸 UI capture received from device")
            return {
                "status": "success",
                "message": "UI snapshot received",
            }
        else:
            logger.warning("⚠️ UI capture request timed out")
            return {
                "status": "timeout",
                "message": "UI capture request timed out after 5 seconds",
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Request UI capture failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Request UI capture failed: {str(e)}",
        )


@router.get("/commands/pending")
async def get_pending_commands(request: Request, device_name: str) -> Dict[str, Any]:
    """
    Get pending commands for a device (polling endpoint).

    Args:
        request: FastAPI request
        device_name: Device identifier

    Returns:
        List of pending commands
    """
    try:
        from services.command_queue import get_command_queue

        command_queue = get_command_queue()
        commands = await command_queue.get_pending_commands(device_name)

        return {
            "status": "success",
            "device_name": device_name,
            "command_count": len(commands),
            "commands": commands,
            "timestamp": int(time.time() * 1000),
        }

    except Exception as e:
        logger.error(f"❌ Failed to get pending commands: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get commands: {str(e)}",
        )


@router.post("/commands/{command_id}/result")
async def report_command_result(
    command_id: str, result: Dict[str, Any], request: Request
) -> Dict[str, Any]:
    """
    Report command execution result from device.

    Args:
        command_id: Command identifier
        result: Execution result
        request: FastAPI request

    Returns:
        Acknowledgment
    """
    try:
        from services.command_queue import get_command_queue

        command_queue = get_command_queue()

        if result.get("success"):
            await command_queue.mark_completed(command_id, result)
        else:
            await command_queue.mark_failed(
                command_id, result.get("error", "Unknown error")
            )

        return {"status": "acknowledged", "command_id": command_id}

    except Exception as e:
        logger.error(f"❌ Failed to report command result: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to report result: {str(e)}",
        )


@router.post("/commands/queue")
async def queue_command(
    device_name: str, command_type: str, payload: Dict[str, Any], request: Request
) -> Dict[str, Any]:
    """
    Queue a command for device execution (Manual Testing Helper).

    Args:
        device_name: Target device name
        command_type: Command type (gesture, launch_app, etc.)
        payload: Command payload/parameters
        request: FastAPI request

    Returns:
        Queued command details
    """
    try:
        from services.command_queue import get_command_queue

        command_queue = get_command_queue()
        command_id = await command_queue.add_command(device_name, command_type, payload)

        logger.info(f"📤 Manual command queued: {command_type} for {device_name}")

        return {
            "status": "queued",
            "command_id": command_id,
            "device_name": device_name,
            "command_type": command_type,
            "message": "Command queued successfully. Device will poll and execute within 2 seconds.",
        }

    except Exception as e:
        logger.error(f"❌ Failed to queue command: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to queue command: {str(e)}",
        )


@router.get("/apps/{device_name}")
async def get_device_apps(device_name: str) -> Dict[str, Any]:
    """Get installed apps for a specific device."""
    try:
        inventory = _load_app_inventory()
        device_apps = inventory.get("devices", {}).get(device_name)

        if not device_apps:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No app inventory found for device: {device_name}",
            )

        return {
            "status": "success",
            "device_name": device_name,
            "app_count": len(device_apps.get("apps", [])),
            "apps": device_apps.get("apps", []),
            "last_updated": device_apps.get("last_updated"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get device apps: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get apps: {str(e)}",
        )


@router.post("/disconnect")
async def disconnect_device(request: Request) -> Dict[str, Any]:
    """
    Disconnect the current device.

    Args:
        request: FastAPI request object

    Returns:
        Disconnect confirmation
    """
    try:
        from services.real_accessibility import real_accessibility_service

        accessibility_service = real_accessibility_service

        device_name = accessibility_service.connected_device
        accessibility_service.disconnect_device()

        logger.info(f"🔌 Device disconnected: {device_name}")
        return {
            "status": "disconnected",
            "message": f"Device {device_name} disconnected successfully",
        }

    except Exception as e:
        logger.error(f"❌ Device disconnect failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Device disconnect failed: {str(e)}",
        )


def _load_app_inventory() -> Dict[str, Any]:
    """Load app inventory from JSON file."""
    try:
        if APP_INVENTORY_FILE.exists():
            with open(APP_INVENTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {
            "_metadata": {
                "description": "Device app inventory",
                "schema_version": "1.0",
            },
            "devices": {},
        }
    except Exception as e:
        logger.error(f"Failed to load app inventory: {e}")
        return {"devices": {}}


def _store_app_inventory(device_name: str, apps: List[AppInfo]) -> None:
    """Store app inventory to JSON file."""
    try:
        inventory = _load_app_inventory()

        # Convert Pydantic models to dicts
        apps_data = [app.model_dump() for app in apps]

        # Update device inventory
        if "devices" not in inventory:
            inventory["devices"] = {}

        inventory["devices"][device_name] = {
            "apps": apps_data,
            "last_updated": int(time.time() * 1000),
            "app_count": len(apps_data),
        }

        # Update metadata
        if "_metadata" not in inventory:
            inventory["_metadata"] = {}
        inventory["_metadata"]["last_updated"] = int(time.time() * 1000)

        # Write to file
        with open(APP_INVENTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(inventory, f, indent=2, ensure_ascii=False)

        logger.info(f"✅ Stored {len(apps_data)} apps for device: {device_name}")

    except Exception as e:
        logger.error(f"Failed to store app inventory: {e}")

@router.post("/gesture-ack")
async def receive_gesture_ack(request: Request):
    """
    Receive gesture acknowledgment from Android device.
    
    Phase 7: Android sends this after executing a gesture to confirm completion.
    
    Expected payload:
    {
        "type": "gesture_ack",
        "command_id": "a1b2c3d4",
        "success": true,
        "error": "",
        "timestamp": 1704556206000
    }
    """
    try:
        body = await request.json()
        
        command_id = body.get("command_id")
        success = body.get("success", False)
        error = body.get("error", "")
        
        if not command_id:
            return {
                "status": "error",
                "message": "Missing command_id in gesture ACK"
            }
        
        logger.info(f"🔔 Received gesture ACK: command_id={command_id}, success={success}")
        
        # Forward to real_accessibility_service to resolve pending gesture
        from services.real_accessibility import real_accessibility_service
        real_accessibility_service.handle_gesture_ack(command_id, success)
        
        return {
            "status": "success",
            "message": f"ACK received for command_id={command_id}",
            "command_id": command_id,
        }
        
    except Exception as e:
        logger.error(f"Failed to process gesture ACK: {e}")
        return {
            "status": "error",
            "message": f"ACK processing failed: {e}"
        }


@router.post("/screen-capture-permission")
async def receive_screen_capture_permission(request: Request):
    """
    Receive screen capture permission result from Android device.
    
    Called by Android when user grants or denies MediaProjection permission.
    Updates screenshot service state to stop spamming permission requests.
    
    Expected payload:
    {
        "type": "screen_capture_permission_result",
        "granted": true,
        "error": null,
        "timestamp": 1704556206000
    }
    """
    try:
        body = await request.json()
        
        granted = body.get("granted", False)
        error = body.get("error")
        
        logger.info(
            f"📸 Screen capture permission result: granted={granted}"
            f"{', error=' + error if error else ''}"
        )
        
        # Forward to screenshot service to update permission state
        from services.screenshot_service import get_screenshot_service
        screenshot_service = get_screenshot_service()
        screenshot_service.handle_permission_result(granted, error)
        
        return {
            "status": "success",
            "message": f"Permission result received: granted={granted}",
            "granted": granted,
        }
        
    except Exception as e:
        logger.error(f"Failed to process screen capture permission result: {e}")
        return {
            "status": "error",
            "message": f"Permission result processing failed: {e}"
        }