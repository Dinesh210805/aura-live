"""
Dynamic agent registry for the Aura orchestration layer.

Provides lookup and factory access to Agent objects by name.
Agents are registered once during application startup (compile_aura_graph)
and can be retrieved by name during runtime to support sub-agent spawning.

The singleton get_agent_registry() is shared across all AuraContext instances
within the same process — agents are singletons (one instance per process).
"""

from __future__ import annotations

import threading
from typing import Dict, List, Optional

from aura.core.agent import Agent
from utils.logger import get_logger

logger = get_logger(__name__)

_registry_lock = threading.Lock()
_global_registry: Optional["AgentRegistry"] = None


class AgentRegistry:
    """
    Thread-safe registry of Agent objects.

    Agents are registered by name and retrieved by name for sub-agent spawning.
    The registry holds live agent instances (not factories) — agents are
    expected to be stateless or to carry only configuration, not per-task state.

    Registration flow::

        registry = get_agent_registry()
        registry.register(CommanderAdapter(commander_agent))
        registry.register(ActorAdapter(actor_agent))

        # Later, in AuraContext.spawn_agent:
        agent = registry.find("commander")
        result = await agent.invoke(input_data, context)
    """

    def __init__(self) -> None:
        self._agents: Dict[str, Agent] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Mutation API
    # ------------------------------------------------------------------

    def register(self, agent: Agent) -> None:
        """
        Register an agent instance.

        If an agent with the same name already exists it is replaced, allowing
        hot-swapping of agent implementations (e.g. upgrading to a new model).
        """
        with self._lock:
            if agent.name in self._agents:
                logger.debug(f"[AgentRegistry] Replacing existing agent: {agent.name!r}")
            self._agents[agent.name] = agent
            logger.info(f"[AgentRegistry] Registered agent: {agent.name!r} — {agent.description}")

    def unregister(self, name: str) -> bool:
        """
        Remove an agent by name.

        Returns:
            True if found and removed, False if not found.
        """
        with self._lock:
            if name in self._agents:
                del self._agents[name]
                logger.info(f"[AgentRegistry] Unregistered agent: {name!r}")
                return True
            logger.warning(f"[AgentRegistry] Agent not found for unregister: {name!r}")
            return False

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def find(self, name: str) -> Optional[Agent]:
        """Return the agent registered under `name`, or None."""
        with self._lock:
            return self._agents.get(name)

    def require(self, name: str) -> Agent:
        """
        Return the agent registered under `name`.

        Raises:
            KeyError: If no agent is registered under that name.
        """
        agent = self.find(name)
        if agent is None:
            raise KeyError(
                f"[AgentRegistry] No agent registered as {name!r}. "
                f"Available: {self.names()}"
            )
        return agent

    def list(self) -> List[Agent]:
        """Return a snapshot of all registered agents."""
        with self._lock:
            return list(self._agents.values())

    def names(self) -> List[str]:
        """Return sorted list of all registered agent names."""
        with self._lock:
            return sorted(self._agents.keys())

    def __len__(self) -> int:
        with self._lock:
            return len(self._agents)

    def __repr__(self) -> str:
        return f"<AgentRegistry agents={self.names()}>"


def get_agent_registry() -> AgentRegistry:
    """Return the process-global AgentRegistry singleton."""
    global _global_registry
    if _global_registry is None:
        with _registry_lock:
            if _global_registry is None:
                _global_registry = AgentRegistry()
                logger.info("[AgentRegistry] Singleton initialized")
    return _global_registry
