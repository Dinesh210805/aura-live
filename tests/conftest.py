"""
Pytest configuration and fixtures.

This file adds the project root to sys.path so that imports work correctly.
"""

import sys
from pathlib import Path

# Add project root and tests/ to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "tests"))
