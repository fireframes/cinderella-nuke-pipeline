"""Cerebro production tracker adapter.

Wraps the py_cerebro database API with lazy connection management and
graceful handling of the case where py_cerebro is not installed (common
outside Windows studio environments).

Set in .env:

    TRACKER_BACKEND=cerebro
    CEREBRO_SERVER=cerebro.studio.local
    CEREBRO_ACCOUNT_PATH=/secrets/cerebro_account.json
    CEREBRO_CARGADOR_ADDRESS=cargador.studio.local
    CEREBRO_TASK_URL_TEMPLATE=/MyShow/Prod/ep{ep:02d}/sq{sq:02d}/sh{sh:03d}/compos
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import threading
from typing import Any, List, Optional

from fastapi import HTTPException

from ...models.schemas import AddReportRequest, StatusModel, TaskModel
from .base import ProductionTracker

try:
    from py_cerebro import cargador, database, dbtypes  # type: ignore[import]
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False


def _require() -> None:
    if not _AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail=(
                "py_cerebro is not installed.  "
                "Install it (Windows only in most studio setups) and restart the server."
            ),
        )


class CerebroTracker(ProductionTracker):

    def __init__(self, settings) -> None:
        self._settings = settings
        self._db: Optional[Any] = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _connect_sync(self) -> Any:
        creds_path = self._settings.CEREBRO_ACCOUNT_PATH
        if not creds_path or not os.path.exists(creds_path):
            raise RuntimeError(
                f"Cerebro credentials file not found: {creds_path!r}. "
                "Set CEREBRO_ACCOUNT_PATH to a JSON file with 'name' and 'pass' fields."
            )
        with open(creds_path, encoding="utf-8") as fh:
            creds = json.load(fh)
        if "name" not in creds or "pass" not in creds:
            raise RuntimeError(
                "Cerebro credentials JSON must contain 'name' and 'pass' fields."
            )
        db = database.Database()
        result = db.connect(creds["name"], creds["pass"], self._settings.CEREBRO_SERVER)
        if result is not None:
            raise RuntimeError(f"Cerebro connection failed: {result}")
        return db

    def _get_db_sync(self) -> Any:
        with self._lock:
            if self._db is None:
                self._db = self._connect_sync()
            return self._db

    async def _get_db(self) -> Any:
        _require()
        try:
            return await asyncio.to_thread(self._get_db_sync)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    def _reset(self) -> None:
        with self._lock:
            self._db = None

    # ------------------------------------------------------------------
    # Task URL construction
    # ------------------------------------------------------------------

    def _build_task_url(self, shot_id: str) -> str:
        if not self._settings.CEREBRO_TASK_URL_TEMPLATE:
            raise HTTPException(
                status_code=500,
                detail="CEREBRO_TASK_URL_TEMPLATE is not configured.",
            )
        pattern = re.compile(self._settings.SHOT_PATTERN)
        m = pattern.fullmatch(shot_id)
        if m is None:
            m = pattern.fullmatch(shot_id.replace("_", "/"))
        if m is None:
            raise HTTPException(
                status_code=400,
                detail=f"shot_id {shot_id!r} does not match SHOT_PATTERN.",
            )
        groups_int = {k: int(v) for k, v in m.groupdict().items()}
        return self._settings.CEREBRO_TASK_URL_TEMPLATE.format(**groups_int)

    # ------------------------------------------------------------------
    # Interface
    # ------------------------------------------------------------------

    async def get_statuses(self) -> List[StatusModel]:
        db = await self._get_db()

        def _sync():
            rows = db.statuses()
            return [
                StatusModel(
                    id=str(row[dbtypes.STATUS_DATA_ID]),
                    name=row[dbtypes.STATUS_DATA_NAME],
                    color=str(row[dbtypes.STATUS_DATA_COLOR]) if row[dbtypes.STATUS_DATA_COLOR] else None,
                )
                for row in (rows or [])
            ]

        try:
            return await asyncio.to_thread(_sync)
        except Exception as exc:
            self._reset()
            raise HTTPException(status_code=503, detail=f"Cerebro error: {exc}") from exc

    async def get_tasks(self, shot_id: str) -> List[TaskModel]:
        db = await self._get_db()
        task_url = self._build_task_url(shot_id)

        def _sync():
            row = db.task_by_url(task_url)
            if not row or row[0] is None:
                return []
            task_id = row[0]
            task_row = db.task(task_id)
            if task_row is None:
                return []
            return [
                TaskModel(
                    id=str(task_id),
                    name=task_row[dbtypes.TASK_DATA_NAME],
                    status_id=str(task_row[dbtypes.TASK_DATA_CC_STATUS]),
                    url=task_url,
                )
            ]

        try:
            return await asyncio.to_thread(_sync)
        except Exception as exc:
            self._reset()
            raise HTTPException(status_code=503, detail=f"Cerebro error: {exc}") from exc

    async def set_status(self, shot_id: str, task_id: str, status_id: str) -> bool:
        db = await self._get_db()

        def _sync():
            db.task_set_status(int(task_id), int(status_id))
            return True

        try:
            return await asyncio.to_thread(_sync)
        except Exception as exc:
            self._reset()
            raise HTTPException(status_code=503, detail=f"Cerebro error: {exc}") from exc

    async def add_report(self, shot_id: str, request: AddReportRequest) -> bool:
        db = await self._get_db()

        def _sync():
            message_id = db.add_report(
                int(request.task_id),
                None,
                request.message,
                request.work_time or 0,
            )
            if message_id is None:
                raise RuntimeError("add_report returned no message ID.")

            if request.preview_path and os.path.exists(request.preview_path):
                carga_obj = cargador.Cargador(
                    self._settings.CEREBRO_CARGADOR_ADDRESS,
                    self._settings.CEREBRO_CARGADOR_NATIVE_PORT,
                    self._settings.CEREBRO_CARGADOR_HTTP_PORT,
                )
                db.add_attachment(
                    message_id,
                    carga_obj,
                    request.preview_path,
                    [],
                    request.message,
                    False,
                )
            return True

        try:
            return await asyncio.to_thread(_sync)
        except Exception as exc:
            self._reset()
            raise HTTPException(status_code=503, detail=f"Cerebro error: {exc}") from exc

    async def health_check(self) -> bool:
        if not _AVAILABLE:
            return False
        try:
            await self._get_db()
            return True
        except HTTPException:
            return False
