"""ShotGrid (formerly Shotgun) production tracker adapter.

Requires:  pip install shotgun_api3

Auth uses script-based credentials (script name + API key), which is the
standard approach for server-side integrations.  Set in .env:

    TRACKER_URL=https://mystudio.shotgrid.autodesk.com
    TRACKER_SCRIPT_NAME=pipeline_bot
    TRACKER_API_KEY=abc123...
    TRACKER_PROJECT=MyShow
    TRACKER_TASK_TYPE=Comp        # optional — filters tasks by step short name
"""
from __future__ import annotations

import asyncio
import os
import threading
from typing import List, Optional

from fastapi import HTTPException

from ...models.schemas import AddReportRequest, StatusModel, TaskModel
from .base import ProductionTracker

try:
    import shotgun_api3  # type: ignore[import]
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False


def _require() -> None:
    if not _AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail=(
                "shotgun_api3 is not installed.  "
                "Run: pip install shotgun_api3"
            ),
        )


class ShotGridTracker(ProductionTracker):

    def __init__(self, settings) -> None:
        self._settings = settings
        self._sg = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _get_sg(self):
        with self._lock:
            if self._sg is None:
                self._sg = shotgun_api3.Shotgun(
                    self._settings.TRACKER_URL,
                    script_name=self._settings.TRACKER_SCRIPT_NAME,
                    api_key=self._settings.TRACKER_API_KEY,
                )
            return self._sg

    def _reset(self) -> None:
        with self._lock:
            self._sg = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _project_id(self, sg) -> int:
        proj = sg.find_one(
            "Project",
            [["name", "is", self._settings.TRACKER_PROJECT]],
            ["id"],
        )
        if not proj:
            raise RuntimeError(
                f"ShotGrid project not found: {self._settings.TRACKER_PROJECT!r}"
            )
        return proj["id"]

    # ------------------------------------------------------------------
    # Interface
    # ------------------------------------------------------------------

    async def get_statuses(self) -> List[StatusModel]:
        _require()

        def _sync():
            sg = self._get_sg()
            schema = sg.schema_field_read("Task", "sg_status_list")
            codes: list = (
                schema.get("sg_status_list", {})
                .get("properties", {})
                .get("valid_values", {})
                .get("value", [])
            )
            return [StatusModel(id=code, name=code) for code in codes]

        try:
            return await asyncio.to_thread(_sync)
        except Exception as exc:
            self._reset()
            raise HTTPException(status_code=503, detail=f"ShotGrid error: {exc}") from exc

    async def get_tasks(self, shot_id: str) -> List[TaskModel]:
        _require()

        def _sync():
            sg = self._get_sg()
            filters = [
                ["project.Project.name", "is", self._settings.TRACKER_PROJECT],
                ["entity.Shot.code", "is", shot_id],
            ]
            if self._settings.TRACKER_TASK_TYPE:
                filters.append(
                    ["step.Step.short_name", "is", self._settings.TRACKER_TASK_TYPE]
                )
            tasks = sg.find(
                "Task",
                filters,
                ["id", "content", "sg_status_list"],
            )
            return [
                TaskModel(
                    id=str(t["id"]),
                    name=t["content"] or "",
                    status_id=t["sg_status_list"] or "",
                    status_name=t["sg_status_list"],
                )
                for t in (tasks or [])
            ]

        try:
            return await asyncio.to_thread(_sync)
        except Exception as exc:
            self._reset()
            raise HTTPException(status_code=503, detail=f"ShotGrid error: {exc}") from exc

    async def set_status(self, shot_id: str, task_id: str, status_id: str) -> bool:
        _require()

        def _sync():
            sg = self._get_sg()
            sg.update("Task", int(task_id), {"sg_status_list": status_id})
            return True

        try:
            return await asyncio.to_thread(_sync)
        except Exception as exc:
            self._reset()
            raise HTTPException(status_code=503, detail=f"ShotGrid error: {exc}") from exc

    async def add_report(self, shot_id: str, request: AddReportRequest) -> bool:
        _require()

        def _sync():
            sg = self._get_sg()
            proj_id = self._project_id(sg)
            note = sg.create(
                "Note",
                {
                    "project": {"type": "Project", "id": proj_id},
                    "note_links": [{"type": "Task", "id": int(request.task_id)}],
                    "content": request.message,
                },
            )
            if request.preview_path and os.path.exists(request.preview_path):
                sg.upload(
                    "Note",
                    note["id"],
                    request.preview_path,
                    field_name="attachments",
                )
            return True

        try:
            return await asyncio.to_thread(_sync)
        except Exception as exc:
            self._reset()
            raise HTTPException(status_code=503, detail=f"ShotGrid error: {exc}") from exc

    async def health_check(self) -> bool:
        if not _AVAILABLE:
            return False
        try:
            def _sync():
                self._get_sg().info()
            await asyncio.to_thread(_sync)
            return True
        except Exception:
            self._reset()
            return False
