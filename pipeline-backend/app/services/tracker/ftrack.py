"""ftrack production tracker adapter.

Requires:  pip install ftrack-python-api

Set in .env:

    TRACKER_URL=https://mystudio.ftrackapp.com
    TRACKER_SCRIPT_NAME=apiuser@studio.com   # ftrack API user (email)
    TRACKER_API_KEY=abc123...
    TRACKER_PROJECT=MyShow
    TRACKER_TASK_TYPE=Comp                    # optional — filters tasks by type name
"""
from __future__ import annotations

import asyncio
import os
import threading
from typing import List

from fastapi import HTTPException

from ...models.schemas import AddReportRequest, StatusModel, TaskModel
from .base import ProductionTracker

try:
    import ftrack_api  # type: ignore[import]
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False


def _require() -> None:
    if not _AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail=(
                "ftrack-python-api is not installed.  "
                "Run: pip install ftrack-python-api"
            ),
        )


class FTrackTracker(ProductionTracker):

    def __init__(self, settings) -> None:
        self._settings = settings
        self._session = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _get_session(self):
        with self._lock:
            if self._session is None:
                self._session = ftrack_api.Session(
                    server_url=self._settings.TRACKER_URL,
                    api_key=self._settings.TRACKER_API_KEY,
                    api_user=self._settings.TRACKER_SCRIPT_NAME,
                )
            return self._session

    def _reset(self) -> None:
        with self._lock:
            self._session = None

    # ------------------------------------------------------------------
    # Interface
    # ------------------------------------------------------------------

    async def get_statuses(self) -> List[StatusModel]:
        _require()

        def _sync():
            session = self._get_session()
            statuses = session.query(
                "select id, name, color from Status where entity_type is Task"
            ).all()
            return [
                StatusModel(
                    id=s["id"],
                    name=s["name"],
                    color=s.get("color"),
                )
                for s in statuses
            ]

        try:
            return await asyncio.to_thread(_sync)
        except Exception as exc:
            self._reset()
            raise HTTPException(status_code=503, detail=f"ftrack error: {exc}") from exc

    async def get_tasks(self, shot_id: str) -> List[TaskModel]:
        _require()

        def _sync():
            session = self._get_session()
            query = (
                f"select id, name, status.id, status.name "
                f"from Task "
                f"where project.name is \"{self._settings.TRACKER_PROJECT}\" "
                f"and parent.name is \"{shot_id}\""
            )
            if self._settings.TRACKER_TASK_TYPE:
                query += f" and type.name is \"{self._settings.TRACKER_TASK_TYPE}\""
            tasks = session.query(query).all()
            return [
                TaskModel(
                    id=t["id"],
                    name=t["name"],
                    status_id=t["status"]["id"],
                    status_name=t["status"]["name"],
                )
                for t in tasks
            ]

        try:
            return await asyncio.to_thread(_sync)
        except Exception as exc:
            self._reset()
            raise HTTPException(status_code=503, detail=f"ftrack error: {exc}") from exc

    async def set_status(self, shot_id: str, task_id: str, status_id: str) -> bool:
        _require()

        def _sync():
            session = self._get_session()
            task = session.get("Task", task_id)
            status = session.get("Status", status_id)
            task["status"] = status
            session.commit()
            return True

        try:
            return await asyncio.to_thread(_sync)
        except Exception as exc:
            self._reset()
            raise HTTPException(status_code=503, detail=f"ftrack error: {exc}") from exc

    async def add_report(self, shot_id: str, request: AddReportRequest) -> bool:
        _require()

        def _sync():
            session = self._get_session()
            task = session.get("Task", request.task_id)
            author = session.query(
                f"User where username is \"{self._settings.TRACKER_SCRIPT_NAME}\""
            ).first()
            note = session.create(
                "Note",
                {"content": request.message, "author": author},
            )
            task["notes"].append(note)
            session.commit()

            if request.preview_path and os.path.exists(request.preview_path):
                server_location = session.query(
                    "Location where name is \"ftrack.server\""
                ).one()
                component = session.create_component(
                    request.preview_path,
                    {"name": os.path.basename(request.preview_path)},
                    location=server_location,
                )
                note["attachments"].append(component)
                session.commit()

            return True

        try:
            return await asyncio.to_thread(_sync)
        except Exception as exc:
            self._reset()
            raise HTTPException(status_code=503, detail=f"ftrack error: {exc}") from exc

    async def health_check(self) -> bool:
        if not _AVAILABLE:
            return False
        try:
            def _sync():
                self._get_session().query("User").first()
            await asyncio.to_thread(_sync)
            return True
        except Exception:
            self._reset()
            return False
