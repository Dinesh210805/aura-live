"""
Configuration package for AURA backend.

This package contains settings and configuration management modules.
"""

from .settings import Settings, get_settings

__all__ = [
    "get_settings",
    "Settings",
]
