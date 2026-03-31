"""Tracker service — thin facade over the pluggable tracker backend.

Routers import from here; they never touch the tracker adapters directly.
"""
from __future__ import annotations

from typing import List

from ..models.schemas import AddReportRequest, StatusModel, TaskModel
from .tracker.factory import get_tracker


async def get_statuses() -> List[StatusModel]:
    return await get_tracker().get_statuses()


async def get_tasks(shot_id: str) -> List[TaskModel]:
    return await get_tracker().get_tasks(shot_id)


async def set_status(shot_id: str, task_id: str, status_id: str) -> bool:
    return await get_tracker().set_status(shot_id, task_id, status_id)


async def add_report(shot_id: str, request: AddReportRequest) -> bool:
    return await get_tracker().add_report(shot_id, request)


async def health_check() -> bool:
    return await get_tracker().health_check()
