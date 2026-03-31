"""Abstract base class for production tracker adapters.

Any tracker (ShotGrid, ftrack, etc.) must implement this interface.
All methods are async; blocking SDK calls should run inside asyncio.to_thread().
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from ...models.schemas import AddReportRequest, StatusModel, TaskModel


class ProductionTracker(ABC):

    @abstractmethod
    async def get_statuses(self) -> List[StatusModel]:
        """Return all task statuses available in the project."""

    @abstractmethod
    async def get_tasks(self, shot_id: str) -> List[TaskModel]:
        """Return tasks assigned to *shot_id* in the configured project."""

    @abstractmethod
    async def set_status(self, shot_id: str, task_id: str, status_id: str) -> bool:
        """Update a task's status.  Returns True on success."""

    @abstractmethod
    async def add_report(self, shot_id: str, request: AddReportRequest) -> bool:
        """Post a note / daily report with optional file attachments."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the tracker is reachable and configured."""
