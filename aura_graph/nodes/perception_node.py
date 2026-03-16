"""
Perception Node for LangGraph.

This node integrates the Perception Controller into the LangGraph workflow.
It requests perception data and makes it available to downstream nodes.
"""

import asyncio
import time
from typing import Dict, Any

from perception.models import PerceptionBundle
from perception.validators import detect_permission_dialog
from services.perception_controller import get_perception_controller
from utils.logger import get_logger
from aura_graph.state import TaskState

# Import workflow step functions
try:
    from aura_graph.core_nodes import add_workflow_step, update_workflow_step
except ImportError:
    # Fallback if circular import
    def add_workflow_step(state, name, status, description, output=None, error=None, execution_time=None):
        """Add workflow step - placeholder."""
        pass
    
    def update_workflow_step(state, name, status, description, output=None, error=None, execution_time=None):
        """Update workflow step - placeholder."""
        pass

logger = get_logger(__name__)

# Retry configuration for perception requests
PERCEPTION_MAX_RETRIES = 3
PERCEPTION_RETRY_DELAY_SECONDS = 1.0  # Delay between retries to allow app to load


async def perception_node(state: TaskState) -> Dict[str, Any]:
    """
    Perception node: Request perception data via Perception Controller.

    This node is the integration point between LangGraph and the Perception Controller.
    It requests perception data based on intent and makes it available to downstream nodes.

    Args:
        state: Current task state with intent

    Returns:
        State update with perception bundle
    """
    start_time = time.time()
    node_name = "Perception"
    
    # Debug: Track perception calls to detect duplicate execution
    session_id = state.get("session_id", "unknown")
    task_id = state.get("task_id", "unknown")
    intent = state.get("intent", {})
    action = intent.get("action", "unknown") if intent else "unknown"
    logger.info(f"🔍 PERCEPTION NODE ENTRY: session={session_id}, task={task_id}, action={action}")

    try:
        logger.info("Perception node: Requesting perception data")
        add_workflow_step(
            state,
            node_name,
            "running",
            "Requesting UI perception data from Perception Controller",
        )

        # Extract intent from state
        intent = state.get("intent")
        if not intent:
            raise ValueError("No intent available for perception request")

        # Get execution history and retry context
        executed_steps = state.get("executed_steps", [])
        retry_count = state.get("retry_count", 0)
        retry_context = {"failed": retry_count > 0} if retry_count > 0 else None

        # Determine action type
        action = intent.get("action", "").lower()
        from config.action_types import NO_UI_ACTIONS
        action_type = "NO_UI_ACTION" if action in NO_UI_ACTIONS else "UI_ACTION"

        # Request perception from controller with retry logic
        # Apps need time to load after being opened, so we retry if perception fails
        controller = get_perception_controller()
        bundle: PerceptionBundle = None
        last_error = None
        
        execution_mode = state.get("execution_mode", "live")
        
        if execution_mode == "simulation":
            logger.info("🧪 SIMULATION MODE: Using mock perception data")
            from perception.models import PerceptionBundle, PerceptionModality, UITreePayload, ScreenshotPayload, ScreenMeta
            import uuid
            
            # Simple 1x1 base64 png
            mock_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+P+/HgAFhAJ/wlseKgAAAABJRU5ErkJggg=="
            
            bundle = PerceptionBundle(
                snapshot_id=str(uuid.uuid4()),
                modality=PerceptionModality.HYBRID,
                screen_meta=ScreenMeta(width=1080, height=2400, orientation="portrait"),
                ui_tree=UITreePayload(
                    elements=[
                        {
                            "resourceId": "com.android.launcher:id/workspace", 
                            "text": "", 
                            "contentDescription": "Home Screen", 
                            "className": "android.view.View",
                            "bounds": {"left": 0, "top": 0, "right": 1080, "bottom": 2400},
                            "clickable": False
                        },
                        {
                            "resourceId": "com.simulation:id/example_button", 
                            "text": "Simulation Action", 
                            "contentDescription": "Simulation Button", 
                            "className": "android.widget.Button",
                            "bounds": {"left": 400, "top": 1000, "right": 700, "bottom": 1200},
                            "clickable": True
                        }
                    ], 
                    screen_width=1080, 
                    screen_height=2400, 
                    timestamp=int(time.time()*1000)
                ),
                screenshot=ScreenshotPayload(
                    screenshot_base64=mock_b64,
                    screen_width=1080,
                    screen_height=2400,
                    timestamp=int(time.time()*1000)
                )
            )
        else:
            for attempt in range(1, PERCEPTION_MAX_RETRIES + 1):
                try:
                    bundle = await controller.request_perception(
                        intent=intent,
                        action_type=action_type,
                        execution_history=executed_steps,
                        retry_context=retry_context,
                    )
                    # Success - break out of retry loop
                    break
                except (ValueError, asyncio.TimeoutError, ConnectionError, OSError) as e:
                    last_error = e
                    error_msg = str(e)

                    # Always retry on transient network/timeout errors
                    is_transient = isinstance(e, (asyncio.TimeoutError, ConnectionError, OSError))
                    # Retry on empty UI tree errors (app still loading)
                    is_empty_tree = "no elements" in error_msg.lower() or "empty" in error_msg.lower()

                    if (is_transient or is_empty_tree) and attempt < PERCEPTION_MAX_RETRIES:
                        logger.warning(
                            f"⏳ Perception attempt {attempt}/{PERCEPTION_MAX_RETRIES} failed "
                            f"({type(e).__name__}), retrying in {PERCEPTION_RETRY_DELAY_SECONDS}s..."
                        )
                        await asyncio.sleep(PERCEPTION_RETRY_DELAY_SECONDS)
                        continue

                    # Non-retryable ValueError or exhausted retries - fail
                    raise
            
            if bundle is None:
                raise last_error or ValueError("Perception failed after retries")

        execution_time = time.time() - start_time

        # Detect permission dialogs (agent should wait, not interact)
        is_permission_dialog = False
        permission_dialog_type = None
        if bundle.ui_tree:
            is_permission_dialog, permission_dialog_type = detect_permission_dialog(bundle.ui_tree)
            if is_permission_dialog:
                logger.warning(
                    f"🚫 Permission dialog detected on screen: type={permission_dialog_type}. "
                    "Agent should wait for user action."
                )

        # Prepare state update
        # Handle modality - it might be an enum or string after deserialization
        modality_str = bundle.modality.value if hasattr(bundle.modality, 'value') else str(bundle.modality)
        
        update_data = {
            "perception_bundle": bundle,  # Store the bundle object, not dict
            "snapshot_id": bundle.snapshot_id,
            "perception_modality": modality_str,
            "status": "perception_complete",
            # Permission dialog detection
            "is_permission_dialog": is_permission_dialog,
            "permission_dialog_type": permission_dialog_type,
        }

        update_workflow_step(
            state,
            node_name,
            "completed",
            f"Perception data obtained: modality={modality_str}, snapshot_id={bundle.snapshot_id}",
            execution_time=execution_time,
        )

        logger.info(
            f"Perception complete: modality={modality_str}, "
            f"snapshot_id={bundle.snapshot_id}"
        )

        return update_data

    except Exception as e:
        execution_time = time.time() - start_time
        error_details = {
            "error_type": type(e).__name__,
            "error_message": str(e),
            "execution_time": execution_time,
        }

        update_workflow_step(
            state,
            node_name,
            "failed",
            f"Perception failed: {str(e)}",
            output=error_details,
            execution_time=execution_time,
        )

        logger.error(f"Perception node failed: {e}")
        return {
            "perception_bundle": None,
            "error_message": f"Perception failed: {str(e)}",
            "status": "perception_failed",
        }
