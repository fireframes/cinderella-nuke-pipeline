"""
Cinderella Configuration System

This module provides access to the configuration system for the Cinderella Nuke tools.
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
