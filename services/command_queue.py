"""
Command queue for backend-to-device communication.
Android device polls this to get pending commands.
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class PendingCommand:
    """A command waiting to be executed by device."""

    command_id: str
    device_name: str
    command_type: str  # "launch_app", "gesture", "send_message", etc.
    payload: Dict[str, Any]
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime = field(
        default_factory=lambda: datetime.now() + timedelta(minutes=5)
    )
    status: str = "pending"  # pending, executing, completed, expired, failed


class CommandQueue:
    """Thread-safe command queue for device communication."""

    def __init__(self):
        self._commands: Dict[str, PendingCommand] = {}
        self._lock = asyncio.Lock()

    async def add_command(
        self, device_name: str, command_type: str, payload: Dict[str, Any]
    ) -> str:
        """
        Add a command to the queue.

        Args:
            device_name: Target device
            command_type: Type of command (launch_app, gesture, etc.)
            payload: Command parameters

        Returns:
            command_id: Unique command identifier
        """
        async with self._lock:
            command_id = f"cmd_{uuid.uuid4().hex[:12]}"

            command = PendingCommand(
                command_id=command_id,
                device_name=device_name,
                command_type=command_type,
                payload=payload,
            )

            self._commands[command_id] = command

            logger.info(
                f"📝 Command queued: {command_type} for device {device_name}",
                extra={"command_id": command_id, "payload": payload},
            )

            return command_id

    async def get_pending_commands(self, device_name: str) -> List[Dict[str, Any]]:
        """
        Get all pending commands for a device.

        Args:
            device_name: Device identifier

        Returns:
            List of pending commands
        """
        async with self._lock:
            # Clean up expired commands
            await self._cleanup_expired()

            # Get pending commands for this device
            pending = [
                {
                    "command_id": cmd.command_id,
                    "command_type": cmd.command_type,
                    "payload": cmd.payload,
                    "created_at": cmd.created_at.isoformat(),
                }
                for cmd in self._commands.values()
                if cmd.device_name == device_name and cmd.status == "pending"
            ]

            # Mark as executing
            for cmd_data in pending:
                self._commands[cmd_data["command_id"]].status = "executing"

            if pending:
                logger.info(f"📤 Sent {len(pending)} commands to device {device_name}")

            return pending

    async def mark_completed(self, command_id: str, result: Dict[str, Any]) -> None:
        """Mark command as completed."""
        async with self._lock:
            if command_id in self._commands:
                self._commands[command_id].status = "completed"
                logger.info(
                    f"✅ Command completed: {command_id}", extra={"result": result}
                )

    async def mark_failed(self, command_id: str, error: str) -> None:
        """Mark command as failed."""
        async with self._lock:
            if command_id in self._commands:
                self._commands[command_id].status = "failed"
                logger.error(f"❌ Command failed: {command_id} - {error}")

    async def get_command_status(self, command_id: str) -> Optional[str]:
        """Get status of a specific command."""
        async with self._lock:
            if command_id in self._commands:
                return self._commands[command_id].status
            return None

    async def _cleanup_expired(self) -> None:
        """Remove expired commands."""
        now = datetime.now()
        expired = [
            cmd_id
            for cmd_id, cmd in self._commands.items()
            if cmd.expires_at < now and cmd.status != "completed"
        ]

        for cmd_id in expired:
            self._commands[cmd_id].status = "expired"
            # Keep for history but mark as expired

        if expired:
            logger.warning(f"🗑️ Marked {len(expired)} commands as expired")


# Global command queue instance
_command_queue: Optional[CommandQueue] = None


def get_command_queue() -> CommandQueue:
    """Get the global command queue instance."""
    global _command_queue
    if _command_queue is None:
        _command_queue = CommandQueue()
        logger.info("Command queue initialized")
    return _command_queue
