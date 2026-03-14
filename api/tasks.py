"""Task execution endpoints."""

import base64
import json
import time
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile, Request

from aura_graph.graph import execute_aura_task, execute_aura_task_from_text
from models.requests import TaskRequest
from models.responses import TaskResponse
from utils.exceptions import AuraBaseException, ConfigurationError
from utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.post("/tasks/execute", response_model=TaskResponse)
async def execute_task(request: TaskRequest, req: Request) -> TaskResponse:
    """
    Execute a voice command task with enhanced error handling.

    Args:
        request: Task execution request.
        req: Raw request to access app state.

    Returns:
        Task execution results with connection status and troubleshooting hints.
    """
    graph_app = getattr(req.app.state, "graph_app", None)

    task_id = f"task_{int(time.time() * 1000)}"

    try:
        logger.info(f"Task execution requested: {task_id}")

        if not graph_app:
            # Fallback: try global access if strictly needed for tests not using lifespan
            try:
                from main import graph_app as global_graph
                graph_app = global_graph
            except ImportError:
                pass
            
            if not graph_app:
                raise ConfigurationError("Graph application not initialized")

        # Pre-flight check for screen-related commands
        input_text = request.text_input if request.input_type == "text" else ""
        execution_mode = (request.config or {}).get("execution_mode")
        
        if "screen" in input_text.lower() and execution_mode != "simulation":
            from services.real_accessibility import real_accessibility_service

            device_info = real_accessibility_service.device_info
            screenshot_data = real_accessibility_service.last_screenshot
            screenshot = screenshot_data.screenshot if screenshot_data else None

            if not device_info:
                logger.warning(
                    f"Screen command requested but no device connected: {input_text}"
                )
                return TaskResponse(
                    task_id=task_id,
                    status="device_not_connected",
                    transcript=input_text,
                    error_message="Android device not connected. Please ensure AURA app is running and registered.",
                    spoken_response="Your Android device is not connected. Please open the AURA app and ensure it's registered with the backend.",
                    execution_time=0.0,
                    debug_info={
                        "issue": "device_not_connected",
                        "hints": [
                            "1. Open AURA app on Android",
                            "2. Enable Accessibility Service",
                            "3. Check backend URL in app settings",
                            "4. Look for device registration confirmation",
                        ],
                    },
                )

            if not screenshot or len(screenshot) < 1000:
                logger.warning(
                    f"Screen command requested but no screenshot available: {input_text}"
                )
                return TaskResponse(
                    task_id=task_id,
                    status="screenshot_unavailable",
                    transcript=input_text,
                    error_message="Screen capture permission not granted. Please enable in AURA app settings.",
                    spoken_response="Screen capture permission is not enabled. Please go to AURA app settings and grant screen capture permission.",
                    execution_time=0.0,
                    debug_info={
                        "issue": "screenshot_permission_missing",
                        "device_connected": True,
                        "screenshot_size": len(screenshot) if screenshot else 0,
                        "hints": [
                            "1. Open AURA app → Settings",
                            "2. Tap 'Request screen capture'",
                            "3. Grant permission when prompted",
                            "4. Restart AURA app",
                        ],
                    },
                )

        # Handle different input types
        if request.input_type == "text":
            # Enable workflow tracking
            exec_config = request.config or {}
            exec_config["track_workflow"] = True
            
            result = await execute_aura_task_from_text(
                app=graph_app,
                text_input=request.text_input,
                config=exec_config,
                thread_id=request.thread_id,
            )
        else:
            try:
                audio_bytes = base64.b64decode(request.audio_data)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid audio data: {e}")

            # Enable workflow tracking
            exec_config = request.config or {}
            exec_config["track_workflow"] = True

            result = await execute_aura_task(
                app=graph_app,
                raw_audio=audio_bytes,
                config=exec_config,
                thread_id=request.thread_id,
            )

        # Store workflow state for visualization
        from api.workflow import store_workflow_state
        
        session_id = result.get("session_id") or task_id
        store_workflow_state(session_id, result)

        # Add device status to debug info
        from services.real_accessibility import real_accessibility_service

        screenshot_data = real_accessibility_service.last_screenshot
        screenshot = screenshot_data.screenshot if screenshot_data else None
        device_status = {
            "device_connected": bool(
                real_accessibility_service.device_info.get("connected")
            ),
            "screenshot_available": bool(screenshot),
            "screenshot_size": len(screenshot) if screenshot else 0,
            "ui_elements_count": (
                len(real_accessibility_service.ui_elements)
                if real_accessibility_service.ui_elements
                else 0
            ),
        }

        response = TaskResponse(
            task_id=task_id,
            status=result.get("status", "unknown"),
            transcript=result.get("transcript", ""),
            intent=result.get("intent"),
            spoken_response=result.get("spoken_response", ""),
            spoken_audio=result.get("spoken_audio"),
            spoken_audio_format=result.get("spoken_audio_format"),
            execution_time=result.get("execution_time", 0.0),
            error_message=result.get("error_message"),
            debug_info={
                **device_status,
                **result.get("debug_info", {}),
            },
        )

        logger.info(f"Task {task_id} completed: {response.status}")
        return response

    except HTTPException:
        raise
    except AuraBaseException as e:
        logger.error(f"AURA error in task {task_id}: {e}")
        return TaskResponse(
            task_id=task_id,
            status="failed",
            error_message=str(e),
            spoken_response="I encountered an error while processing your request.",
        )
    except Exception as e:
        logger.error(f"Unexpected error in task {task_id}: {e}")
        return TaskResponse(
            task_id=task_id,
            status="failed",
            error_message="Internal server error",
            spoken_response="I'm sorry, I encountered an unexpected error.",
        )


@router.post("/tasks/execute-file")
async def execute_task_from_file(
    file: UploadFile = File(...),
    config: Optional[str] = None,
    thread_id: Optional[str] = None,
) -> TaskResponse:
    """
    Execute a voice command task from uploaded audio file.

    Args:
        file: Uploaded audio file.
        config: Optional JSON configuration string.
        thread_id: Optional thread ID for state persistence.

    Returns:
        Task execution results.
    """
    task_id = f"file_task_{int(time.time() * 1000)}"

    try:
        logger.info(f"File task execution requested: {task_id}")

        if not file.content_type or not file.content_type.startswith("audio/"):
            raise HTTPException(status_code=400, detail="File must be an audio file")

        audio_bytes = await file.read()

        if len(audio_bytes) == 0:
            raise HTTPException(status_code=400, detail="Empty audio file")

        task_config = None
        if config:
            try:
                task_config = json.loads(config)
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=400, detail="Invalid JSON configuration"
                )

        request = TaskRequest(
            audio_data=base64.b64encode(audio_bytes).decode(),
            config=task_config,
            thread_id=thread_id,
        )

        return await execute_task(request)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"File task error {task_id}: {e}")
        return TaskResponse(
            task_id=task_id,
            status="failed",
            error_message="Failed to process audio file",
            spoken_response="I couldn't process the audio file you provided.",
        )
