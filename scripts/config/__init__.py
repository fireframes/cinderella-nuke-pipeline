"""
Pipeline Configuration System

This module provides access to the configuration system for the Nuke pipeline tools.
"""

from .config_loader import (
    CONFIG,
    get_project_config,
    project_root_settings
)

__all__ = [
    'CONFIG',
    'get_project_config',
    'project_root_settings'
]
