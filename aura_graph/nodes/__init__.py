"""
AURA Graph Nodes Package.

Contains specialized nodes for goal-driven execution:
- perception_node: Captures UI state via Perception Controller
- coordinator_node: Multi-agent goal execution (perceive→decide→act→verify loop)
"""

from .perception_node import perception_node
from .coordinator_node import coordinator_node, initialize_coordinator

__all__ = [
    "perception_node",
    "coordinator_node",
    "initialize_coordinator",
]
