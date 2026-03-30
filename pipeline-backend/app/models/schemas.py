"""
Pydantic schemas for the Shot Manager pipeline backend.

All path fields are normalized to forward slashes on the way in.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, field_validator


# ---------------------------------------------------------------------------
# Shot / render layer
# ---------------------------------------------------------------------------

class RenderLayer(BaseModel):
    """A single render layer found in a shot's render directory."""

    name: str    # Base name with version stripped, e.g. "beauty"
    path: str    # Absolute forward-slash path to the versioned layer dir
    version: int # Version number parsed from the dir name; 0 if unversioned

    @field_validator("path", mode="before")
    @classmethod
    def _fwd(cls, v: str) -> str:
        return v.replace("\\", "/") if v else v


class ShotModel(BaseModel):
    """Canonical shot representation returned by the backend."""

    shot_id: str            # e.g. "ep01_sq05_sh001"
    episode: str            # Numeric string from the ep group, e.g. "01"
    sequence: str           # Numeric string from the sq group, e.g. "05"
    shot: str               # Numeric string from the sh group, e.g. "001"
    render_path: str        # Absolute path to the render sub-dir (contains EXRs)
    comp_path: str          # Absolute path to the shot's comp dir
    precomp_path: str       # Absolute path to the shot's light_precomp dir
    cam_path: Optional[str] = None  # Path to shot_camera.abc; None if not found

    @field_validator("render_path", "comp_path", "precomp_path", mode="before")
    @classmethod
    def _fwd_required(cls, v: str) -> str:
        return v.replace("\\", "/") if v else v

    @field_validator("cam_path", mode="before")
    @classmethod
    def _fwd_optional(cls, v: Optional[str]) -> Optional[str]:
        return v.replace("\\", "/") if v else v


class ShotDetail(ShotModel):
    """ShotModel extended with render layers; returned by GET /shots/{shot_id}."""

    render_layers: List[RenderLayer] = []


# ---------------------------------------------------------------------------
# Cerebro
# ---------------------------------------------------------------------------

class StatusModel(BaseModel):
    """A Cerebro task status."""

    id: int
    name: str
    color: Optional[str] = None  # Hex color string if provided by Cerebro


class TaskModel(BaseModel):
    """A Cerebro task associated with a shot."""

    id: int
    name: str
    status_id: int                   # Effective (calculated) status ID
    status_name: Optional[str] = None
    url: str                         # Cerebro task URL, e.g. "/MyShow/ep01/.../compos"


class SetStatusRequest(BaseModel):
    task_id: int
    status_id: int


class AddReportRequest(BaseModel):
    task_id: int
    message: str
    preview_path: Optional[str] = None  # Path to .mov or image to attach
    scene_path: Optional[str] = None    # Path to .nk scene to attach
    work_time: Optional[int] = None     # Minutes spent on task


# ---------------------------------------------------------------------------
# Scripts / thumbnails
# ---------------------------------------------------------------------------

class ScriptResponse(BaseModel):
    """Response from comp / precomp script creation endpoints."""

    path: str       # Absolute forward-slash path to the .nk file
    shot_id: str
    created: bool   # True = newly written; False = already existed (skipped overwrite)

    @field_validator("path", mode="before")
    @classmethod
    def _fwd(cls, v: str) -> str:
        return v.replace("\\", "/") if v else v


class ThumbnailResponse(BaseModel):
    """Response from GET /shots/{shot_id}/thumbnail."""

    path: str
    shot_id: str
    generated: bool  # True = ffmpeg was invoked; False = returned from cache

    @field_validator("path", mode="before")
    @classmethod
    def _fwd(cls, v: str) -> str:
        return v.replace("\\", "/") if v else v


# ---------------------------------------------------------------------------
# Scan / health
# ---------------------------------------------------------------------------

class ScanResponse(BaseModel):
    """Response from POST /shots/scan."""

    count: int
    from_cache: bool


class HealthResponse(BaseModel):
    """Response from GET /health."""

    status: str               # "ok" or "degraded"
    render_path_ok: bool
    cerebro_ok: bool
    detail: Optional[str] = None
