"""Tracker factory — returns the right ProductionTracker based on TRACKER_BACKEND."""
from __future__ import annotations

from functools import lru_cache

from ...config import Settings, get_settings
from .base import ProductionTracker


@lru_cache(maxsize=1)
def get_tracker() -> ProductionTracker:
    """Return the singleton tracker instance for the configured backend."""
    settings = get_settings()
    backend = (settings.TRACKER_BACKEND or "").lower().strip()

    if backend == "shotgrid":
        from .shotgrid import ShotGridTracker
        return ShotGridTracker(settings)

    if backend == "ftrack":
        from .ftrack import FTrackTracker
        return FTrackTracker(settings)

    if backend == "cerebro":
        from .cerebro import CerebroTracker
        return CerebroTracker(settings)

    from .null import NullTracker
    return NullTracker()
