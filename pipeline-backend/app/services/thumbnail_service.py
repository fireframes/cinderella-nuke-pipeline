"""
Thumbnail generation service.

Given a shot_id, finds the latest versioned .mov in the comp/mov directory,
checks for a cached thumbnail, and generates one with ffmpeg if needed.
All ffmpeg calls run in a thread pool so they don't block the event loop.
"""
from __future__ import annotations

import asyncio
import os
import re
import subprocess
from typing import Optional

from fastapi import HTTPException

from ..config import get_settings
from ..models.schemas import ThumbnailResponse
from .shot_scanner import get_shot


def _find_latest_mov(mov_dir: str) -> Optional[str]:
    """Return the path to the highest-versioned .mov in *mov_dir*, or None."""
    if not os.path.isdir(mov_dir):
        return None
    try:
        versioned: list[tuple[int, str]] = []
        for fname in os.listdir(mov_dir):
            if not fname.lower().endswith(".mov"):
                continue
            m = re.search(r"_v(\d+)\.mov$", fname, re.IGNORECASE)
            if m:
                versioned.append((int(m.group(1)), fname))
        if not versioned:
            return None
        _, best = max(versioned, key=lambda x: x[0])
        return os.path.join(mov_dir, best).replace("\\", "/")
    except OSError:
        return None


def _make_thumbnail_sync(mov_path: str, thumb_dir: str) -> str:
    """Generate a JPEG thumbnail for *mov_path* and return its path.

    Raises RuntimeError on failure.
    """
    settings = get_settings()

    os.makedirs(thumb_dir, exist_ok=True)

    stem = os.path.splitext(os.path.basename(mov_path))[0]
    thumb_path = os.path.join(thumb_dir, f"{stem}_thumb.jpg").replace("\\", "/")

    if os.path.exists(thumb_path):
        return thumb_path

    # Probe duration to decide seek position.
    seek_time = settings.THUMBNAIL_SEEK_TIME
    try:
        probe = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                mov_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if probe.returncode == 0:
            duration = float(probe.stdout.strip())
            if duration <= seek_time:
                seek_time = settings.THUMBNAIL_FALLBACK_SEEK
    except (ValueError, subprocess.TimeoutExpired, FileNotFoundError):
        pass

    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-ss", str(seek_time),
            "-i", mov_path,
            "-vf", "scale=1024:429:force_original_aspect_ratio=decrease",
            "-vframes", "1",
            "-y",
            thumb_path,
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0 or not os.path.exists(thumb_path):
        raise RuntimeError(
            f"ffmpeg failed (exit {result.returncode}): {result.stderr.strip()}"
        )

    return thumb_path


async def generate_thumbnail(shot_id: str) -> ThumbnailResponse:
    """Return a thumbnail for *shot_id*, generating it on demand if absent.

    Raises HTTP 404 if the shot or its .mov cannot be found.
    Raises HTTP 500 if ffmpeg fails.
    """
    shot = await get_shot(shot_id)
    if shot is None:
        raise HTTPException(status_code=404, detail=f"Shot not found: {shot_id}")

    mov_dir = f"{shot.comp_path}/mov"
    thumb_dir = f"{shot.comp_path}/mov/.thumb"

    mov_path = await asyncio.to_thread(_find_latest_mov, mov_dir)
    if mov_path is None:
        raise HTTPException(
            status_code=404,
            detail=f"No versioned .mov found in {mov_dir}",
        )

    # Check cache before spawning ffmpeg.
    stem = os.path.splitext(os.path.basename(mov_path))[0]
    thumb_path = f"{thumb_dir}/{stem}_thumb.jpg"
    if os.path.exists(thumb_path):
        return ThumbnailResponse(path=thumb_path, shot_id=shot_id, generated=False)

    try:
        path = await asyncio.to_thread(_make_thumbnail_sync, mov_path, thumb_dir)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except FileNotFoundError:
        raise HTTPException(
            status_code=500,
            detail="ffmpeg / ffprobe not found in PATH.",
        )

    return ThumbnailResponse(path=path, shot_id=shot_id, generated=True)
