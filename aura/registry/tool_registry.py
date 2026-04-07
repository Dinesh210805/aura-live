"""
Dynamic tool registry for the Aura orchestration layer.

Provides thread-safe registration, unregistration, and lookup of Tool objects.
Mirrors the reference coding agent's dynamic tool list pattern, where tools can
be added or removed without restarting the system.

The singleton get_tool_registry() is initialized once and shared across all
AuraContext instances within the same process.
"""

from __future__ import annotations

import threading
from typing import Dict, List, Optional

from aura.core.tool import Tool
from utils.logger import get_logger

logger = get_logger(__name__)

_registry_lock = threading.Lock()
_global_registry: Optional["ToolRegistry"] = None


class ToolRegistry:
    """
    Thread-safe registry of Tool objects.

    All mutations (register/unregister) acquire a lock so that concurrent
    agent threads never see a partially-updated registry.

    Discovery flow:
        ToolRegistry.register(tool)   → makes tool available
        ToolRegistry.find("tap")      → returns TapTool instance or None
        ToolRegistry.list()           → returns all registered tools
        ToolRegistry.unregister("tap")→ removes tool (hot-swap)
    """

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Mutation API
    # ------------------------------------------------------------------

    def register(self, tool: Tool) -> None:
        """
        Register a tool. If a tool with the same name already exists, it is
        replaced (allows hot-swapping implementations at runtime).
        """
        with self._lock:
            if tool.name in self._tools:
                logger.debug(f"[ToolRegistry] Replacing existing tool: {tool.name!r}")
            self._tools[tool.name] = tool
            logger.info(f"[ToolRegistry] Registered tool: {tool.name!r}")

    def unregister(self, name: str) -> bool:
        """
        Remove a tool by name.

        Returns:
            True if the tool was found and removed, False if not found.
        """
        with self._lock:
            if name in self._tools:
                del self._tools[name]
                logger.info(f"[ToolRegistry] Unregistered tool: {name!r}")
                return True
            logger.warning(f"[ToolRegistry] Tool not found for unregister: {name!r}")
            return False

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def find(self, name: str) -> Optional[Tool]:
        """Return the tool registered under `name`, or None."""
        with self._lock:
            return self._tools.get(name)

    def list(self) -> List[Tool]:
        """Return a snapshot of all registered tools (copy, thread-safe)."""
        with self._lock:
            return list(self._tools.values())

    def names(self) -> List[str]:
        """Return sorted list of all registered tool names."""
        with self._lock:
            return sorted(self._tools.keys())

    def __len__(self) -> int:
        with self._lock:
            return len(self._tools)

    def __repr__(self) -> str:
        return f"<ToolRegistry tools={self.names()}>"


def get_tool_registry() -> ToolRegistry:
    """Return the process-global ToolRegistry singleton."""
    global _global_registry
    if _global_registry is None:
        with _registry_lock:
            if _global_registry is None:
                _global_registry = ToolRegistry()
                logger.info("[ToolRegistry] Singleton initialized")
    return _global_registry
