"""
Improved Gesture Execution Service.

Centralized, simplified gesture execution with better error handling and coordination.
"""

import asyncio
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from config.action_types import NO_UI_ACTIONS
from services.real_accessibility import real_accessibility_service
from utils.app_inventory_utils import get_app_inventory_manager
from utils.logger import get_logger

logger = get_logger(__name__)


class GestureType(Enum):
    """Supported gesture types."""
    TAP = "tap"
    SWIPE = "swipe"
    LONG_PRESS = "long_press"
    SCROLL = "scroll"
    TYPE_TEXT = "type"
    DOUBLE_TAP = "double_tap"


class ExecutionStrategy(Enum):
    """Gesture execution strategies."""
    WEBSOCKET = "websocket"  # Instant via WebSocket (fastest)
    COMMAND_QUEUE = "command_queue"  # Via polling queue (reliable)
    DIRECT = "direct"  # Direct API call (fallback)


@dataclass
class GestureResult:
    """Result of a gesture execution."""
    success: bool
    gesture_type: str
    execution_time: float
    strategy_used: str
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


@dataclass
class ExecutionPlan:
    """Complete execution plan with all steps."""
    steps: List[Dict[str, Any]]
    total_steps: int
    estimated_time: float
    requires_ui_refresh: bool = False


class GestureExecutor:
    """
    Simplified, centralized gesture execution service.
    
    Key improvements:
    1. Single source of truth for gesture execution
    2. Automatic strategy selection (WebSocket > Queue > Direct)
    3. Built-in coordinate normalization
    4. Better error handling and retry logic
    5. Execution state tracking
    """

    def __init__(self):
        """Initialize gesture executor."""
        self.execution_history: List[GestureResult] = []
        self.current_plan: Optional[ExecutionPlan] = None
        self._screen_size: Tuple[int, int] = (1080, 2400)
        
        logger.info("✅ Gesture executor initialized")

    def _looks_like_phone_number(self, text: str) -> bool:
        """Check if text looks like a phone number."""
        import re
        # Match phone patterns: +91xxx, 91xxx, or 10+ digits
        phone_pattern = r'[\+\d][\d\s\-\(\)]{8,}'
        return bool(re.search(phone_pattern, text))

    async def execute_plan(self, action_plan: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Execute a complete action plan.
        
        Args:
            action_plan: List of action steps to execute
            
        Returns:
            Execution summary with results for each step
        """
        if not action_plan:
            return self._create_result(False, 0, 0, [], ["Empty action plan"])
        
        # Update screen size
        await self._update_screen_size()
        
        # Create execution plan
        self.current_plan = self._create_execution_plan(action_plan)
        
        start_time = time.time()
        executed_steps = []
        errors = []
        
        logger.info(f"🎯 Executing plan with {len(action_plan)} steps")
        
        for i, action in enumerate(action_plan):
            step_num = i + 1
            step_start = time.time()
            
            try:
                logger.info(f"  Step {step_num}/{len(action_plan)}: {action.get('action', 'unknown')}")
                
                # Execute single action
                result = await self._execute_single_action(action)
                
                step_result = {
                    "step": step_num,
                    "action": action.get("action"),
                    "success": result.success,
                    "execution_time": time.time() - step_start,
                    "strategy": result.strategy_used,
                    "details": result.details or {}
                }
                
                if not result.success:
                    step_result["error"] = result.error
                    errors.append(f"Step {step_num}: {result.error}")
                    logger.warning(f"  ❌ Step {step_num} failed: {result.error}")
                else:
                    logger.info(f"  ✅ Step {step_num} completed")
                
                executed_steps.append(step_result)
                self.execution_history.append(result)
                
                # Inter-step delay for UI stability
                if step_num < len(action_plan):
                    delay = action.get("post_delay", 0.5)
                    await asyncio.sleep(delay)
                    
            except Exception as e:
                error_msg = f"Step {step_num} exception: {str(e)}"
                logger.error(error_msg, exc_info=True)
                errors.append(error_msg)
                
                executed_steps.append({
                    "step": step_num,
                    "action": action.get("action", "unknown"),
                    "success": False,
                    "error": str(e),
                    "execution_time": time.time() - step_start
                })
        
        # Create result summary
        success_count = sum(1 for step in executed_steps if step["success"])
        total_time = time.time() - start_time
        
        return self._create_result(
            success=len(errors) == 0,
            total_steps=len(action_plan),
            success_count=success_count,
            executed_steps=executed_steps,
            errors=errors,
            total_time=total_time
        )

    async def _execute_single_action(self, action: Dict[str, Any]) -> GestureResult:
        """
        Execute a single action with automatic strategy selection.
        
        Args:
            action: Action dictionary with type and parameters
            
        Returns:
            GestureResult with execution outcome
        """
        start_time = time.time()
        action_type = action.get("action", "").lower()
        
        # Route to appropriate handler
        try:
            # Communication actions (send_message, call, etc.) - use deep link flow
            communication_actions = ["send_message", "send_whatsapp", "send_sms", "send_email", 
                                      "call", "make_call", "dial", "video_call"]
            if action_type in communication_actions:
                result = await self._execute_app_launch(action)
            # App launch actions - require package lookup
            elif action_type in ["open_app", "launch_app", "launch", "open"]:
                result = await self._execute_app_launch(action)
            # System actions (home, back, torch, etc.) - NO UI needed
            elif action_type in NO_UI_ACTIONS:
                result = await self._execute_system_action(action)
            elif action_type in ["tap", "click", "press"]:
                result = await self._execute_tap(action)
            elif action_type == "swipe":
                result = await self._execute_swipe(action)
            elif action_type == "long_press":
                result = await self._execute_long_press(action)
            elif action_type in ("scroll", "scroll_up", "scroll_down", "scroll_left", "scroll_right"):
                # Normalise directional variants: scroll_down → direction=down, etc.
                if action_type != "scroll" and "direction" not in action:
                    action = {**action, "direction": action_type.split("_", 1)[1]}
                result = await self._execute_scroll(action)
            elif action_type in ["type", "input", "type_text"]:
                result = await self._execute_type(action)
            elif action_type in ["open_app", "launch_app", "launch", "open"]:
                result = await self._execute_app_launch(action)
            elif action_type == "deep_link":
                result = await self._execute_deep_link(action)
            elif action_type == "wait":
                result = await self._execute_wait(action)
            else:
                result = GestureResult(
                    success=False,
                    gesture_type=action_type,
                    execution_time=0,
                    strategy_used="none",
                    error=f"Unknown action type: {action_type}"
                )
            
            result.execution_time = time.time() - start_time
            return result
            
        except Exception as e:
            return GestureResult(
                success=False,
                gesture_type=action_type,
                execution_time=time.time() - start_time,
                strategy_used="failed",
                error=str(e)
            )

    async def _execute_tap(self, action: Dict[str, Any]) -> GestureResult:
        """Execute tap gesture with explicit pixel coordinates."""
        # Phase 5: Require explicit format field
        coord_format = action.get("format")
        if not coord_format:
            logger.error("❌ Missing format field in tap action")
            return GestureResult(
                success=False,
                gesture_type="tap",
                execution_time=0,
                strategy_used="none",
                error="Missing format field - coordinates must declare format"
            )
        
        coordinates = self._extract_coordinates(action)
        if not coordinates:
            return GestureResult(
                success=False,
                gesture_type="tap",
                execution_time=0,
                strategy_used="none",
                error="No valid coordinates provided"
            )
        
        x, y = coordinates
        
        # Phase 5: Use coordinates directly (format=pixels means already in screen coords)
        if coord_format == "pixels":
            gesture_x, gesture_y = int(x), int(y)
        else:
            # Normalized 0-1 format (legacy support)
            gesture_x = int(x * self._screen_size[0])
            gesture_y = int(y * self._screen_size[1])
        
        # Build gesture data
        gesture_data = {
            "action": "tap",
            "x": gesture_x,
            "y": gesture_y,
            "format": coord_format,
            "timestamp": time.time()
        }
        
        logger.info(f"📍 Executing tap: x={gesture_x}, y={gesture_y}, format={coord_format}")
        
        # Execute via best available strategy
        strategy, success, error = await self._send_gesture(gesture_data)
        
        return GestureResult(
            success=success,
            gesture_type="tap",
            execution_time=0,
            strategy_used=strategy,
            error=error,
            details={"x": gesture_data["x"], "y": gesture_data["y"]}
        )

    async def _execute_swipe(self, action: Dict[str, Any]) -> GestureResult:
        """Execute swipe gesture with explicit pixel coordinates."""
        # Phase 5: Require explicit format field
        coord_format = action.get("format")
        if not coord_format:
            logger.error("❌ Missing format field in swipe action")
            return GestureResult(
                success=False,
                gesture_type="swipe",
                execution_time=0,
                strategy_used="none",
                error="Missing format field - coordinates must declare format"
            )
        
        # Extract coordinates - support multiple formats
        coords = action.get("coordinates", {})
        x1 = y1 = x2 = y2 = None
        
        # Format 1: Navigator output (start_x, start_y, end_x, end_y)
        if "start_x" in action and "start_y" in action:
            x1, y1 = action["start_x"], action["start_y"]
            x2, y2 = action["end_x"], action["end_y"]
        # Format 2: Nested coordinates.start/end
        elif "start" in coords and "end" in coords:
            x1, y1 = coords["start"]["x"], coords["start"]["y"]
            x2, y2 = coords["end"]["x"], coords["end"]["y"]
        # Format 3: Flat coordinates.x1/y1/x2/y2
        elif all(k in coords for k in ["x1", "y1", "x2", "y2"]):
            x1, y1 = coords["x1"], coords["y1"]
            x2, y2 = coords["x2"], coords["y2"]
        # Format 4: Flat action x1/y1/x2/y2
        elif all(k in action for k in ["x1", "y1", "x2", "y2"]):
            x1, y1 = action["x1"], action["y1"]
            x2, y2 = action["x2"], action["y2"]
        
        if x1 is None or y1 is None or x2 is None or y2 is None:
            return GestureResult(
                success=False,
                gesture_type="swipe",
                execution_time=0,
                strategy_used="none",
                error="Invalid swipe coordinates - missing start_x/y or end_x/y"
            )
        
        duration = action.get("duration", 500)
        
        # Phase 5: Use coordinates directly based on declared format
        if coord_format == "pixels":
            gx1, gy1, gx2, gy2 = int(x1), int(y1), int(x2), int(y2)
        else:
            # Normalized 0-1 format (legacy support)
            gx1 = int(x1 * self._screen_size[0])
            gy1 = int(y1 * self._screen_size[1])
            gx2 = int(x2 * self._screen_size[0])
            gy2 = int(y2 * self._screen_size[1])
        
        gesture_data = {
            "action": "swipe",
            "x1": gx1,
            "y1": gy1,
            "x2": gx2,
            "y2": gy2,
            "duration": duration,
            "format": coord_format,
            "timestamp": time.time()
        }
        
        logger.info(f"📍 Executing swipe: ({gx1},{gy1}) → ({gx2},{gy2}), format={coord_format}")
        
        strategy, success, error = await self._send_gesture(gesture_data)
        
        return GestureResult(
            success=success,
            gesture_type="swipe",
            execution_time=0,
            strategy_used=strategy,
            error=error,
            details=gesture_data
        )

    async def _execute_scroll(self, action: Dict[str, Any]) -> GestureResult:
        """Execute scroll gesture by direction."""
        direction = action.get("direction", "down").lower()
        distance = action.get("distance", 0.5)  # Fraction of screen
        
        # Convert direction to swipe coordinates
        width, height = self._screen_size
        center_x = width // 2
        
        if direction == "down":
            start = (center_x, int(height * 0.7))
            end = (center_x, int(height * 0.3))
        elif direction == "up":
            start = (center_x, int(height * 0.3))
            end = (center_x, int(height * 0.7))
        elif direction == "left":
            start = (int(width * 0.7), height // 2)
            end = (int(width * 0.3), height // 2)
        elif direction == "right":
            start = (int(width * 0.3), height // 2)
            end = (int(width * 0.7), height // 2)
        else:
            return GestureResult(
                success=False,
                gesture_type="scroll",
                execution_time=0,
                strategy_used="none",
                error=f"Invalid scroll direction: {direction}"
            )
        
        gesture_data = {
            "action": "swipe",
            "x1": start[0],
            "y1": start[1],
            "x2": end[0],
            "y2": end[1],
            "duration": 500,
            "timestamp": time.time()
        }
        
        strategy, success, error = await self._send_gesture(gesture_data)
        
        return GestureResult(
            success=success,
            gesture_type="scroll",
            execution_time=0,
            strategy_used=strategy,
            error=error,
            details={"direction": direction}
        )

    async def _execute_long_press(self, action: Dict[str, Any]) -> GestureResult:
        """Execute long press gesture with explicit pixel coordinates."""
        # Phase 5: Require explicit format field
        coord_format = action.get("format")
        if not coord_format:
            logger.error("❌ Missing format field in long_press action")
            return GestureResult(
                success=False,
                gesture_type="long_press",
                execution_time=0,
                strategy_used="none",
                error="Missing format field - coordinates must declare format"
            )
        
        coordinates = self._extract_coordinates(action)
        if not coordinates:
            return GestureResult(
                success=False,
                gesture_type="long_press",
                execution_time=0,
                strategy_used="none",
                error="No valid coordinates"
            )
        
        x, y = coordinates
        
        # Phase 5: Use coordinates directly based on declared format
        if coord_format == "pixels":
            gesture_x, gesture_y = int(x), int(y)
        else:
            # Normalized 0-1 format (legacy support)
            gesture_x = int(x * self._screen_size[0])
            gesture_y = int(y * self._screen_size[1])
        
        gesture_data = {
            "action": "long_press",
            "x": gesture_x,
            "y": gesture_y,
            "duration": 1000,
            "format": coord_format,
            "timestamp": time.time()
        }
        
        logger.info(f"📍 Executing long_press: x={gesture_x}, y={gesture_y}, format={coord_format}")
        
        strategy, success, error = await self._send_gesture(gesture_data)
        
        return GestureResult(
            success=success,
            gesture_type="long_press",
            execution_time=0,
            strategy_used=strategy,
            error=error
        )

    async def _execute_type(self, action: Dict[str, Any]) -> GestureResult:
        """Execute text input."""
        text = action.get("text") or action.get("content", "")
        if not text:
            return GestureResult(
                success=False,
                gesture_type="type",
                execution_time=0,
                strategy_used="none",
                error="No text provided"
            )
        
        gesture_data = {
            "action": "type",
            "text": text,
            "timestamp": time.time()
        }
        
        strategy, success, error = await self._send_gesture(gesture_data)
        
        return GestureResult(
            success=success,
            gesture_type="type",
            execution_time=0,
            strategy_used=strategy,
            error=error,
            details={"text_length": len(text)}
        )

    async def _execute_app_launch(self, action: Dict[str, Any]) -> GestureResult:
        """Execute app launch via intent with optional deep link support."""
        app_name = action.get("app_name") or action.get("target") or action.get("recipient")
        package_name = action.get("package_name")
        
        # Lookup package name if not provided
        if not package_name and app_name:
            inventory = get_app_inventory_manager()
            candidates = inventory.get_package_candidates(app_name.lower().strip())
            if candidates:
                package_name = candidates[0]
        
        if not package_name:
            return GestureResult(
                success=False,
                gesture_type="launch_app",
                execution_time=0,
                strategy_used="none",
                error=f"Package name not found for: {app_name}"
            )
        
        # Try to use deep link for communication actions
        deep_link_uri = None
        deep_link_scheme = None  # Track scheme for send button logic
        communication_actions = ["send_message", "send_whatsapp", "send_sms", "send_email", 
                                 "call", "make_call", "dial", "video_call"]
        action_type = action.get("action", "").lower()
        
        if action_type in communication_actions or any(k in action for k in ["recipient", "phone", "message", "content"]):
            try:
                from utils.deep_link_utils import DeepLinkManager
                from utils.types import IntentObject
                from services.contact_resolver import ContactResolver
                deep_link_manager = DeepLinkManager()
                
                # Convert action dict to format compatible with deep link manager
                intent_data = {
                    "action": action.get("action", ""),
                    "recipient": action.get("recipient") or action.get("phone"),
                    "content": action.get("content") or action.get("message"),
                    "parameters": action.get("parameters", {})
                }
                
                # Parameters might be flattened into action dict by Navigator
                # Check for app in both action root and parameters
                if "app" in action:
                    intent_data["parameters"]["app"] = action["app"]
                if "app_name" in action:
                    intent_data["parameters"]["app"] = action["app_name"]
                
                # Try to resolve contact name to phone number if recipient doesn't contain a phone pattern
                recipient = intent_data.get("recipient")
                if recipient and not self._looks_like_phone_number(recipient):
                    logger.info(f"🔍 Attempting contact resolution for: {recipient}")
                    contact_resolver = ContactResolver(real_accessibility_service)
                    
                    # Register resolver so WebSocket handler can route results to it
                    real_accessibility_service.register_contact_resolver(contact_resolver)
                    
                    try:
                        phone_number = await contact_resolver.resolve_contact(recipient)
                        
                        if phone_number:
                            logger.info(f"✅ Contact resolved: {recipient} → {phone_number}")
                            intent_data["recipient"] = phone_number
                        else:
                            logger.warning(f"⚠️ Could not resolve contact: {recipient}")
                    finally:
                        # Unregister after resolution attempt
                        real_accessibility_service.unregister_contact_resolver()
                
                # Check if deep link is viable
                can_use, app_package, scheme = deep_link_manager.can_use_deep_link(intent_data)
                
                if can_use and scheme:
                    deep_link_scheme = scheme  # Save scheme for later use
                    logger.info(f"✅ Deep link viable: scheme={scheme}, app={app_package}")
                    # Create IntentObject for building URI
                    intent_obj = IntentObject(
                        action=intent_data["action"],
                        recipient=intent_data["recipient"],
                        content=intent_data["content"],
                        parameters=intent_data["parameters"]
                    )
                    
                    # Build the deep link URI
                    uri = deep_link_manager.build_deep_link_uri(intent_obj, scheme, app_package)
                    if uri:
                        deep_link_uri = uri
                        # Override package name with deep link target
                        if app_package:
                            package_name = app_package
                        logger.info(f"🔗 Using deep link: {uri} for package: {package_name}")
                    else:
                        logger.warning(f"⚠️ Deep link URI construction failed for scheme: {scheme}")
                        logger.warning(f"   recipient={intent_data.get('recipient')}, content={intent_data.get('content')}")
                else:
                    reason = f"No phone number found in recipient or content" if action_type in communication_actions else "Unknown reason"
                    logger.warning(f"⚠️ Deep link not available: {reason}")
                    logger.warning(f"   action={action_type}, recipient={intent_data.get('recipient')}, content={intent_data.get('content')}")
            except Exception as e:
                logger.warning(f"⚠️ Deep link construction error: {e}")
        
        # Launch via intent (with optional deep link)
        result = await real_accessibility_service.launch_app_via_intent(package_name, deep_link_uri=deep_link_uri)
        
        # If deep link was used for messaging, add a follow-up tap on send button
        if deep_link_uri and deep_link_scheme in ["whatsapp", "sms"]:
            logger.info(f"📤 Deep link opened (scheme={deep_link_scheme}), waiting for app to load then tapping send button...")
            await asyncio.sleep(2.5)  # Wait for WhatsApp/messaging app to load UI
            
            try:
                # Get UI tree to find send button
                from services.ui_tree_service import get_ui_tree_service
                ui_service = get_ui_tree_service()
                logger.info("🔍 Requesting UI tree to find send button...")
                ui_tree = await ui_service.request_ui_tree(timeout=4.0)
                
                if ui_tree and ui_tree.get("elements"):
                    logger.info(f"📋 Got UI tree with {len(ui_tree['elements'])} elements")
                    
                    # Find send button (common content descriptions and text)
                    send_keywords = ["send", "submit", "enviar", "kirim", "भेजें"]  # Multi-language
                    send_button = None
                    
                    for element in ui_tree["elements"]:
                        text = (element.get("text") or "").lower()
                        desc = (element.get("contentDescription") or "").lower()
                        
                        if element.get("clickable") and any(kw in text or kw in desc for kw in send_keywords):
                            send_button = element
                            logger.info(f"✅ Found send button: text='{element.get('text')}', desc='{element.get('contentDescription')}'")
                            break
                    
                    if send_button:
                        bounds = send_button.get("bounds", {})
                        center_x = bounds.get("centerX")
                        center_y = bounds.get("centerY")
                        
                        if center_x and center_y:
                            logger.info(f"📍 Tapping send button at ({center_x}, {center_y})...")
                            tap_result = await real_accessibility_service.dispatch_gesture({
                                "action": "tap",
                                "x": center_x,
                                "y": center_y,
                                "duration": 100
                            })
                            
                            if tap_result.get("success"):
                                logger.info("✅ Send button tapped successfully via accessibility!")
                                await asyncio.sleep(0.5)  # Brief wait for message to send
                            else:
                                logger.warning(f"⚠️ Failed to tap send button: {tap_result.get('error')}")
                        else:
                            logger.warning(f"⚠️ Send button found but missing coordinates: {bounds}")
                    else:
                        logger.warning(f"⚠️ Could not find send button in UI tree (checked {len(ui_tree['elements'])} elements)")
                        # Log some clickable elements for debugging
                        clickable = [e for e in ui_tree["elements"] if e.get("clickable")][:5]
                        logger.debug(f"Sample clickable elements: {[e.get('contentDescription') or e.get('text') for e in clickable]}")
                else:
                    logger.warning(f"⚠️ Could not get UI tree to find send button (ui_tree={bool(ui_tree)})")
            except Exception as e:
                logger.error(f"❌ Error tapping send button: {e}")
        
        if isinstance(result, dict):
            success = result.get("success", False)
            error = result.get("error") if not success else None
        else:
            success = bool(result)
            error = None if success else "Launch failed"
        
        return GestureResult(
            success=success,
            gesture_type="launch_app",
            execution_time=0,
            strategy_used="deep_link" if deep_link_uri else "intent",
            error=error,
            details={"package": package_name, "deep_link": deep_link_uri}
        )

    async def _execute_deep_link(self, action: Dict[str, Any]) -> GestureResult:
        """Execute deep link."""
        uri = action.get("uri") or action.get("url")
        if not uri:
            return GestureResult(
                success=False,
                gesture_type="deep_link",
                execution_time=0,
                strategy_used="none",
                error="No URI provided"
            )
        
        result = await real_accessibility_service.open_deep_link(uri)
        
        return GestureResult(
            success=result.get("success", False),
            gesture_type="deep_link",
            execution_time=0,
            strategy_used="intent",
            error=result.get("error"),
            details={"uri": uri}
        )

    async def _execute_wait(self, action: Dict[str, Any]) -> GestureResult:
        """Execute wait/delay."""
        duration = action.get("duration", 1.0)
        await asyncio.sleep(duration)
        
        return GestureResult(
            success=True,
            gesture_type="wait",
            execution_time=duration,
            strategy_used="sleep",
            details={"duration": duration}
        ) 
    async def _execute_system_action(self, action: Dict[str, Any]) -> GestureResult:
        """
        Execute system-level actions (home, back, torch, volume, etc.).
        These actions don't require UI analysis or coordinates.
        """
        action_type = action.get("action", "").lower()
        
        # Map action to Android gesture type
        system_action_map = {
            # Navigation
            "home": "home",
            "back": "back",
            "recent_apps": "recent_apps",
            # Torch/Flashlight
            "control_torch": "toggle_flashlight",
            "control_flashlight": "toggle_flashlight",
            "toggle_flashlight": "toggle_flashlight",
            "flashlight_on": "toggle_flashlight",
            "flashlight_off": "toggle_flashlight",
            # Volume
            "volume_up": "volume_up",
            "volume_down": "volume_down",
            "mute": "mute",
            "unmute": "unmute",
            # Brightness
            "brightness_up": "brightness_up",
            "brightness_down": "brightness_down",
            # Network
            "wifi_on": "wifi_on",
            "wifi_off": "wifi_off",
            "bluetooth_on": "bluetooth_on",
            "bluetooth_off": "bluetooth_off",
            # Screenshot
            "screenshot": "screenshot",
            "take_screenshot": "screenshot",
        }
        
        mapped_action = system_action_map.get(action_type)
        if not mapped_action:
            return GestureResult(
                success=False,
                gesture_type=action_type,
                execution_time=0,
                strategy_used="none",
                error=f"System action not mapped: {action_type}"
            )
        
        # Build gesture data
        gesture_data = {
            "action": mapped_action,
            "timestamp": time.time()
        }
        
        # Add state parameter for toggle actions if provided
        if "state" in action.get("parameters", {}):
            gesture_data["state"] = action["parameters"]["state"]
        
        # Execute via best available strategy
        strategy, success, error = await self._send_gesture(gesture_data)
        
        return GestureResult(
            success=success,
            gesture_type=action_type,
            execution_time=0,
            strategy_used=strategy,
            error=error,
            details={"mapped_action": mapped_action}
        )


    async def _send_gesture(self, gesture_data: Dict[str, Any]) -> Tuple[str, bool, Optional[str]]:
        """
        Send gesture via WebSocket (the only supported channel for gestures).
        
        Phase 4: Eliminated command queue and direct API fallbacks.
        WebSocket is now the ONLY delivery channel for gestures.
        
        Returns:
            (strategy_used, success, error_message)
        """
        # Phase 4: WebSocket is the ONLY gesture delivery channel
        if not real_accessibility_service.has_websocket():
            logger.error("❌ WebSocket required for gesture execution - no connection available")
            return ("failed", False, "WebSocket required for gesture execution")
        
        try:
            result = await real_accessibility_service.dispatch_gesture(gesture_data)
            if result.get("success"):
                return ("websocket", True, None)
            else:
                error_msg = result.get("error", "Gesture dispatch failed")
                logger.error(f"❌ Gesture dispatch failed: {error_msg}")
                return ("websocket", False, error_msg)
        except Exception as e:
            logger.error(f"❌ WebSocket gesture execution failed: {e}")
            return ("failed", False, str(e))

    def _extract_coordinates(self, action: Dict[str, Any]) -> Optional[Tuple[float, float]]:
        """Extract coordinates from various action formats."""
        coords = action.get("coordinates", {})
        
        if isinstance(coords, list) and len(coords) >= 2:
            return (coords[0], coords[1])
        elif isinstance(coords, dict):
            if "x" in coords and "y" in coords:
                return (coords["x"], coords["y"])
            elif "centerX" in coords and "centerY" in coords:
                return (coords["centerX"], coords["centerY"])
        
        # Try direct fields
        if "x" in action and "y" in action:
            return (action["x"], action["y"])
        
        return None

    def _normalize_coordinates(self, x: float, y: float) -> Tuple[float, float]:
        """
        DEPRECATED (Phase 5): Normalize pixel coordinates to 0-1 range.
        
        This method is no longer used - all gestures now require explicit
        format declaration. Kept for reference during transition.
        """
        import warnings
        warnings.warn(
            "_normalize_coordinates is deprecated. Use explicit format field instead.",
            DeprecationWarning,
            stacklevel=2
        )
        width, height = self._screen_size
        return (x / width if width > 0 else 0, y / height if height > 0 else 0)

    async def _update_screen_size(self):
        """Update screen size from device."""
        try:
            screen_info = await real_accessibility_service.get_screen_info()
            self._screen_size = (screen_info["width"], screen_info["height"])
        except Exception as e:
            logger.warning(f"Failed to update screen size: {e}")

    def _create_execution_plan(self, actions: List[Dict[str, Any]]) -> ExecutionPlan:
        """Create execution plan with metadata."""
        total_steps = len(actions)
        estimated_time = sum(action.get("timeout", 5.0) for action in actions)
        requires_refresh = any(
            action.get("action") in ["open_app", "deep_link"]
            for action in actions
        )
        
        return ExecutionPlan(
            steps=actions,
            total_steps=total_steps,
            estimated_time=estimated_time,
            requires_ui_refresh=requires_refresh
        )

    def _create_result(
        self,
        success: bool,
        total_steps: int,
        success_count: int,
        executed_steps: List[Dict],
        errors: List[str],
        total_time: float = 0
    ) -> Dict[str, Any]:
        """Create standardized execution result."""
        return {
            "success": success,
            "total_steps": total_steps,
            "successful_steps": success_count,
            "failed_steps": total_steps - success_count,
            "execution_steps": executed_steps,
            "errors": errors,
            "total_execution_time": total_time,
            "summary": f"Executed {success_count}/{total_steps} steps successfully"
        }


# Global instance
_gesture_executor: Optional[GestureExecutor] = None


def get_gesture_executor() -> GestureExecutor:
    """Get global gesture executor instance."""
    global _gesture_executor
    if _gesture_executor is None:
        _gesture_executor = GestureExecutor()
    return _gesture_executor
