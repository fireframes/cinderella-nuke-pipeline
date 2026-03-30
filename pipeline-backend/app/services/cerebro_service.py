"""
Cerebro integration service.

Wraps the py_cerebro database API with lazy connection management, credential
loading, and graceful handling of the case where py_cerebro is not installed
(common outside Windows studio environments).

All blocking psycopg2 calls run inside asyncio.to_thread().
If py_cerebro is unavailable, every public method raises HTTP 503.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import threading
from typing import Any, List, Optional

from fastapi import HTTPException

from ..config import get_settings
from ..models.schemas import AddReportRequest, StatusModel, TaskModel

# ---------------------------------------------------------------------------
# Optional import — py_cerebro is Windows-only in many studio setups.
# ---------------------------------------------------------------------------
try:
    from py_cerebro import cargador, database, dbtypes  # type: ignore[import]

    _CEREBRO_AVAILABLE = True
except ImportError:
    _CEREBRO_AVAILABLE = False


def _require_cerebro() -> None:
    if not _CEREBRO_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail=(
                "py_cerebro is not installed.  "
                "Install it (Windows only in most studio setups) and restart the server."
            ),
        )


# ---------------------------------------------------------------------------
# Lazy connection singleton
# ---------------------------------------------------------------------------

_db: Optional[Any] = None  # database.Database instance once connected
_db_lock = threading.Lock()


def _connect_sync() -> Any:
    """Create and return a connected database.Database.  Raises on failure."""
    settings = get_settings()

    creds_path = settings.CEREBRO_ACCOUNT_PATH
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
    result = db.connect(creds["name"], creds["pass"], settings.CEREBRO_SERVER)
    if result is not None:
        raise RuntimeError(f"Cerebro connection failed: {result}")

    return db


def _get_db_sync() -> Any:
    """Return the module-level DB singleton, connecting on first call."""
    global _db
    with _db_lock:
        if _db is None:
            _db = _connect_sync()
        return _db


async def _get_db() -> Any:
    """Async wrapper — runs the blocking connect in a thread pool."""
    _require_cerebro()
    try:
        return await asyncio.to_thread(_get_db_sync)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _reset_connection() -> None:
    """Force reconnection on the next call (e.g. after a connection error)."""
    global _db
    with _db_lock:
        _db = None


# ---------------------------------------------------------------------------
# Task URL construction
# ---------------------------------------------------------------------------

def _build_task_url(shot_id: str) -> str:
    """Derive the Cerebro task URL for *shot_id* from CEREBRO_TASK_URL_TEMPLATE."""
    settings = get_settings()

    if not settings.CEREBRO_TASK_URL_TEMPLATE:
        raise HTTPException(
            status_code=500,
            detail="CEREBRO_TASK_URL_TEMPLATE is not configured.",
        )

    pattern = re.compile(settings.SHOT_PATTERN)
    m = pattern.fullmatch(shot_id)
    # shot_id uses _ as separator, not /; try matching via SHOT_DIR_FORMAT
    if m is None:
        # shot_id looks like ep01_sq05_sh001 — replace _ with / and retry
        alt = shot_id.replace("_", "/")
        m = pattern.fullmatch(alt)
    if m is None:
        raise HTTPException(
            status_code=400,
            detail=f"shot_id {shot_id!r} does not match SHOT_PATTERN.",
        )

    groups_int = {k: int(v) for k, v in m.groupdict().items()}
    return settings.CEREBRO_TASK_URL_TEMPLATE.format(**groups_int)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def get_statuses() -> List[StatusModel]:
    """Return all Cerebro statuses."""
    db = await _get_db()

    def _sync():
        rows = db.statuses()
        return [
            StatusModel(
                id=row[dbtypes.STATUS_DATA_ID],
                name=row[dbtypes.STATUS_DATA_NAME],
                color=str(row[dbtypes.STATUS_DATA_COLOR]) if row[dbtypes.STATUS_DATA_COLOR] else None,
            )
            for row in (rows or [])
        ]

    try:
        return await asyncio.to_thread(_sync)
    except Exception as exc:
        _reset_connection()
        raise HTTPException(status_code=503, detail=f"Cerebro error: {exc}") from exc


async def get_tasks(shot_id: str) -> List[TaskModel]:
    """Return the Cerebro task(s) associated with *shot_id*."""
    db = await _get_db()
    task_url = _build_task_url(shot_id)

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
                id=task_id,
                name=task_row[dbtypes.TASK_DATA_NAME],
                status_id=task_row[dbtypes.TASK_DATA_CC_STATUS],
                url=task_url,
            )
        ]

    try:
        return await asyncio.to_thread(_sync)
    except Exception as exc:
        _reset_connection()
        raise HTTPException(status_code=503, detail=f"Cerebro error: {exc}") from exc


async def set_status(shot_id: str, task_id: int, status_id: int) -> bool:
    """Set *task_id* status to *status_id* in Cerebro.  Returns True on success."""
    db = await _get_db()

    def _sync():
        db.task_set_status(task_id, status_id)
        return True

    try:
        return await asyncio.to_thread(_sync)
    except Exception as exc:
        _reset_connection()
        raise HTTPException(status_code=503, detail=f"Cerebro error: {exc}") from exc


async def add_report(shot_id: str, request: AddReportRequest) -> bool:
    """Add a report message (and optional attachments) to a Cerebro task."""
    db = await _get_db()
    settings = get_settings()

    def _sync():
        message_id = db.add_report(
            request.task_id,
            None,                   # new message (no parent)
            request.message,
            request.work_time or 0,
        )
        if message_id is None:
            raise RuntimeError("add_report returned no message ID.")

        if request.preview_path and os.path.exists(request.preview_path):
            carga_obj = cargador.Cargador(
                settings.CEREBRO_CARGADOR_ADDRESS,
                settings.CEREBRO_CARGADOR_NATIVE_PORT,
                settings.CEREBRO_CARGADOR_HTTP_PORT,
            )
            db.add_attachment(
                message_id,
                carga_obj,
                request.preview_path,
                [],                # thumbnails generated by client or omitted
                request.message,
                False,             # not as_link
            )

        return True

    try:
        return await asyncio.to_thread(_sync)
    except Exception as exc:
        _reset_connection()
        raise HTTPException(status_code=503, detail=f"Cerebro error: {exc}") from exc


async def health_check() -> bool:
    """Return True if a Cerebro connection can be established, False otherwise."""
    if not _CEREBRO_AVAILABLE:
        return False
    try:
        await _get_db()
        return True
    except HTTPException:
        return False
