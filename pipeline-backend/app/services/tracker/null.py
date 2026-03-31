"""Null tracker — used when TRACKER_BACKEND is empty or unrecognised.

Every method raises HTTP 503 with a clear message so the rest of the
backend (shot scanning, thumbnails, scripts) continues working normally.
"""
from __future__ import annotations

from typing import List

from fastapi import HTTPException

from ...models.schemas import AddReportRequest, StatusModel, TaskModel
from .base import ProductionTracker

_MSG = (
    "No production tracker is configured.  "
    "Set TRACKER_BACKEND to 'shotgrid' or 'ftrack' in your .env file."
)


class NullTracker(ProductionTracker):

    async def get_statuses(self) -> List[StatusModel]:
        raise HTTPException(status_code=503, detail=_MSG)

    async def get_tasks(self, shot_id: str) -> List[TaskModel]:
        raise HTTPException(status_code=503, detail=_MSG)

    async def set_status(self, shot_id: str, task_id: str, status_id: str) -> bool:
        raise HTTPException(status_code=503, detail=_MSG)

    async def add_report(self, shot_id: str, request: AddReportRequest) -> bool:
        raise HTTPException(status_code=503, detail=_MSG)

    async def health_check(self) -> bool:
        return False
