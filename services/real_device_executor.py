"""Real Device Execution Service.

Executes actual automation commands on a connected Android device via the
AccessibilityService integration.
"""

import asyncio
from typing import Any, Dict, List

from services.gesture_executor import get_gesture_executor
from utils.logger import get_logger

logger = get_logger(__name__)


class RealDeviceExecutor:
    """
    Executes automation commands on real Android device.
    
    Now uses the simplified GestureExecutor for better reliability.
    """

    def __init__(self):
        """Initialize real device executor."""
        self.gesture_executor = get_gesture_executor()
        self.execution_history = []
        
        logger.info("✅ Real device executor initialized")

    async def execute_action_plan(
        self, action_plan: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Execute complete action plan on real device.

        Args:
            action_plan: List of actions to execute.

        Returns:
            Execution results dictionary.
        """
        logger.info(f"📋 Executing action plan with {len(action_plan)} steps")
        
        # Delegate to gesture executor
        result = await self.gesture_executor.execute_plan(action_plan)
        
        # Store in history
        self.execution_history.append(result)
        
        return result

    async def execute_gesture(
        self, gesture_command: Dict[str, Any], device_name: str = None
    ) -> bool:
        """
        Execute gesture command on device using new gesture injection system.

        Args:
            gesture_command: Gesture command dict from gesture_builder
            device_name: Optional device name (auto-detected if None)

        Returns:
            True if command was queued successfully

        Note:
            Actual gesture execution is asynchronous. Success means
            command was queued, not that gesture completed successfully.
            Check Android logs for actual execution result.

        Example:
            >>> from services.gesture_builder import build_tap
            >>> command = build_tap(0.5, 0.5)
            >>> await executor.execute_gesture(command)
            True
        """
        try:
            import json
            from pathlib import Path

            from services.command_queue import get_command_queue
            from services.real_accessibility import real_accessibility_service

            command_queue = get_command_queue()

            # Get device name: explicit parameter > accessibility service > inventory file
            if not device_name:
                device_name = real_accessibility_service.connected_device

            if not device_name:
                # Try to get device name from app inventory file
                try:
                    inventory_path = Path("device_app_inventory.json")
                    if inventory_path.exists():
                        with open(inventory_path) as f:
                            inventory = json.load(f)
                            devices = inventory.get("devices", {})
                            if devices:
                                # Get first device
                                device_name = list(devices.keys())[0]
                                logger.info(f"📱 Auto-detected device: {device_name}")
                except Exception as e:
                    logger.debug(f"Could not load device from inventory: {e}")

            if not device_name:
                logger.error("❌ No device connected. Make sure:")
                logger.error("   1. Backend is running")
                logger.error("   2. Android app is running")
                logger.error("   3. Device has registered (opened the app)")
                return False

            command_id = await command_queue.add_command(
                device_name=device_name, command_type="gesture", payload=gesture_command
            )

            logger.info(
                f"✅ Gesture queued: {gesture_command.get('gesture_type')} (ID: {command_id}) for {device_name}"
            )
            return True

        except Exception as e:
            logger.error(f"❌ Failed to queue gesture: {e}")
            return False

    async def execute_gesture_sequence(
        self,
        gestures: List[Dict[str, Any]],
        delay_between: float = 1.0,
        device_name: str = None,
    ) -> int:
        """
        Execute multiple gestures in sequence with delays.

        Args:
            gestures: List of gesture commands
            delay_between: Seconds to wait between gestures

        Returns:
            Number of gestures successfully queued

        Example:
            >>> from services.gesture_builder import build_tap, build_scroll
            >>> gestures = [
            ...     build_tap(0.5, 0.3),
            ...     build_scroll("down"),
            ...     build_tap(0.5, 0.7)
            ... ]
            >>> count = await executor.execute_gesture_sequence(gestures)
            >>> print(f"Queued {count}/3 gestures")
        """
        success_count = 0

        logger.info(f"🎯 Executing gesture sequence: {len(gestures)} gestures")

        for i, gesture in enumerate(gestures):
            gesture_type = gesture.get("gesture_type", "unknown")

            if await self.execute_gesture(gesture, device_name=device_name):
                success_count += 1
                logger.info(f"✅ Gesture {i+1}/{len(gestures)} queued: {gesture_type}")
            else:
                logger.error(
                    f"❌ Gesture {i+1}/{len(gestures)} failed to queue: {gesture_type}"
                )

            if i < len(gestures) - 1:  # Don't delay after last gesture
                logger.debug(f"⏳ Waiting {delay_between}s before next gesture")
                await asyncio.sleep(delay_between)

        logger.info(
            f"🎯 Gesture sequence completed: {success_count}/{len(gestures)} queued successfully"
        )
        return success_count


# Global instance for use across the application
real_device_executor = RealDeviceExecutor()

# Alias for backwards compatibility
RealDeviceExecutorService = RealDeviceExecutor

