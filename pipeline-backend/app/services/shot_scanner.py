"""
Shot scanner service.

Walks RENDER_PATH and discovers shots by matching directory paths against
SHOT_PATTERN.  Results are cached to a JSON file with a configurable TTL.

Key design constraints:
- SHOT_PATTERN is always compiled from config — no hardcoded startswith() checks.
- SHOT_SCAN_DEPTH controls how many directory levels are walked; it is set once
  in config to match the depth implied by SHOT_PATTERN (default: 3 for ep/sq/sh).
- A shot is valid only when its render sub-directory contains at least one EXR.
- All blocking I/O runs inside asyncio.to_thread().
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from ..config import Settings, get_settings
from ..models.schemas import RenderLayer, ShotDetail, ShotModel


# ---------------------------------------------------------------------------
# EXR sequence helpers
# ---------------------------------------------------------------------------

def _has_exr(directory: str) -> bool:
    """Return True as soon as one .exr file is found anywhere directly inside
    the directory or any of its immediate sub-directories (render layers)."""
    try:
        with os.scandir(directory) as top:
            for entry in top:
                if not entry.is_dir():
                    continue
                with os.scandir(entry.path) as files:
                    for f in files:
                        if f.name.lower().endswith(".exr"):
                            return True
    except OSError:
        pass
    return False


def _find_exr_sequence(layer_dir: str) -> Optional[tuple[str, int, int]]:
    """Scan *layer_dir* and return the primary EXR sequence as
    (nuke_format_path, first_frame, last_frame) or None if no EXRs found.

    Handles filenames like:
      beauty_v02.1001.exr
      ep01_sq05_sh001_beauty.%04d.exr  (already a format string — skip)
      beauty.0001.exr
    """
    try:
        exr_files = sorted(
            f for f in os.listdir(layer_dir) if f.lower().endswith(".exr")
        )
    except OSError:
        return None

    if not exr_files:
        return None

    # Match: <prefix><frame_digits>.exr   (frame = 3-8 consecutive digits)
    frame_re = re.compile(r"^(.*?)(\d{3,8})(\.exr)$", re.IGNORECASE)

    frames: list[int] = []
    prefix: Optional[str] = None

    for fname in exr_files:
        m = frame_re.match(fname)
        if not m:
            continue
        if prefix is None:
            prefix = m.group(1)
        if m.group(1) == prefix:
            frames.append(int(m.group(2)))

    if not frames or prefix is None:
        # Unrecognised naming — return the first file as a bare path.
        bare = os.path.join(layer_dir, exr_files[0]).replace("\\", "/")
        return (bare, 0, 0)

    # Determine zero-padding from the first file's frame digits.
    first_fname_match = frame_re.match(exr_files[0])
    padding = len(first_fname_match.group(2)) if first_fname_match else 4

    seq_path = os.path.join(layer_dir, f"{prefix}%0{padding}d.exr").replace("\\", "/")
    return (seq_path, min(frames), max(frames))


# ---------------------------------------------------------------------------
# Render layer discovery
# ---------------------------------------------------------------------------

def _get_render_layers_sync(render_path: str) -> List[RenderLayer]:
    """List render layers inside *render_path*.

    Directories may be versioned (e.g. ``beauty_v02``).  We group by base name
    and keep only the highest version of each group.
    """
    if not os.path.isdir(render_path):
        return []

    # groups: base_name → list of (version_int, dir_name)
    groups: dict[str, list[tuple[int, str]]] = {}

    try:
        with os.scandir(render_path) as it:
            for entry in it:
                if not entry.is_dir():
                    continue
                m = re.match(r"^(.+?)_v(\d+)$", entry.name)
                if m:
                    base, ver = m.group(1), int(m.group(2))
                else:
                    base, ver = entry.name, 0
                groups.setdefault(base, []).append((ver, entry.name))
    except OSError:
        return []

    layers: List[RenderLayer] = []
    for base_name, versions in sorted(groups.items()):
        latest_ver, latest_dir = max(versions, key=lambda x: x[0])
        full_path = os.path.join(render_path, latest_dir).replace("\\", "/")
        layers.append(RenderLayer(name=base_name, path=full_path, version=latest_ver))

    return layers


async def get_render_layers(render_path: str) -> List[RenderLayer]:
    return await asyncio.to_thread(_get_render_layers_sync, render_path)


# ---------------------------------------------------------------------------
# Shot building
# ---------------------------------------------------------------------------

def _build_shot(
    groups: dict[str, str],
    shot_dir: str,
    settings: Settings,
) -> Optional[ShotModel]:
    """Build a ShotModel from the regex match groups and the matched directory.

    Returns None if the shot has no EXRs in its render sub-directory.
    """
    shot_dir_fwd = shot_dir.replace("\\", "/")
    render_path = f"{shot_dir_fwd}/{settings.SHOT_RENDER_SUBDIR}"

    if not _has_exr(render_path):
        return None

    dir_rel = settings.SHOT_DIR_FORMAT.format(**groups)
    comp_root = settings.COMP_PATH.replace("\\", "/").rstrip("/")
    comp_path = f"{comp_root}/{dir_rel}/comp"
    precomp_path = f"{comp_root}/{dir_rel}/light_precomp"

    # Camera: prefer CACHE_PATH_NEW, fall back to CACHE_PATH_OLD.
    cam_path: Optional[str] = None
    for cache_root in (settings.CACHE_PATH_NEW, settings.CACHE_PATH_OLD):
        if not cache_root:
            continue
        candidate = "/".join([
            cache_root.replace("\\", "/").rstrip("/"),
            dir_rel,
            settings.SHOT_CAM_SUBDIR,
            settings.SHOT_CAM_FILENAME,
        ])
        if os.path.exists(candidate):
            cam_path = candidate
            break

    return ShotModel(
        shot_id=settings.SHOT_ID_FORMAT.format(**groups),
        episode=groups.get(settings.SHOT_EP_GROUP, ""),
        sequence=groups.get(settings.SHOT_SQ_GROUP, ""),
        shot=groups.get(settings.SHOT_SH_GROUP, ""),
        render_path=render_path,
        comp_path=comp_path,
        precomp_path=precomp_path,
        cam_path=cam_path,
    )


# ---------------------------------------------------------------------------
# Directory walker
# ---------------------------------------------------------------------------

def _walk(
    root_path: str,
    current_path: str,
    pattern: re.Pattern,
    shots: list[ShotModel],
    settings: Settings,
    depth: int,
    max_depth: int,
) -> None:
    """Recursively scan directories up to *max_depth* levels below *root_path*.

    At each entry, we try a fullmatch of the relative path against *pattern*.
    Entries that don't match and haven't reached max depth are descended into.
    """
    if depth >= max_depth:
        return

    try:
        with os.scandir(current_path) as it:
            for entry in it:
                if not entry.is_dir():
                    continue

                # Build the path relative to the scan root, normalised to /.
                rel = os.path.relpath(entry.path, root_path).replace("\\", "/")

                m = pattern.fullmatch(rel)
                if m:
                    shot = _build_shot(m.groupdict(), entry.path, settings)
                    if shot:
                        shots.append(shot)
                    # Don't recurse inside a matched shot directory.
                else:
                    _walk(root_path, entry.path, pattern, shots, settings, depth + 1, max_depth)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def _cache_file(settings: Settings) -> Path:
    base = settings.SHOT_CACHE_PATH or "/tmp"
    return Path(base) / "shot_manager_cache.json"


def _load_cache(settings: Settings) -> Optional[List[ShotModel]]:
    path = _cache_file(settings)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        ts = datetime.fromisoformat(data["timestamp"])
        # Ensure tz-aware comparison.
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        now = datetime.now(tz=timezone.utc)
        ttl_seconds = settings.SHOT_CACHE_TTL_HOURS * 3600
        if (now - ts).total_seconds() < ttl_seconds:
            return [ShotModel(**s) for s in data["shots"]]
    except Exception:
        pass
    return None


def _save_cache(shots: List[ShotModel], settings: Settings) -> None:
    path = _cache_file(settings)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "shots": [s.model_dump() for s in shots],
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _scan_sync() -> List[ShotModel]:
    """Blocking filesystem walk.  Intended to run in a thread pool."""
    settings = get_settings()

    if not settings.RENDER_PATH or not os.path.isdir(settings.RENDER_PATH):
        return []

    pattern = re.compile(settings.SHOT_PATTERN)
    shots: list[ShotModel] = []
    _walk(
        root_path=settings.RENDER_PATH,
        current_path=settings.RENDER_PATH,
        pattern=pattern,
        shots=shots,
        settings=settings,
        depth=0,
        max_depth=settings.SHOT_SCAN_DEPTH,
    )
    shots.sort(key=lambda s: s.shot_id)
    return shots


async def scan_shots(force: bool = False) -> List[ShotModel]:
    """Return the full shot list, using the on-disk cache when still fresh.

    Pass ``force=True`` to bypass the cache and rescan unconditionally.
    """
    settings = get_settings()

    if not force:
        cached = await asyncio.to_thread(_load_cache, settings)
        if cached is not None:
            return cached

    shots = await asyncio.to_thread(_scan_sync)
    await asyncio.to_thread(_save_cache, shots, settings)
    return shots


async def get_shot(shot_id: str) -> Optional[ShotModel]:
    """Return a single ShotModel by shot_id, or None if not found."""
    shots = await scan_shots()
    for s in shots:
        if s.shot_id == shot_id:
            return s
    return None


async def get_shot_detail(shot_id: str) -> Optional[ShotDetail]:
    """Return a ShotDetail (ShotModel + render layers) for *shot_id*."""
    shot = await get_shot(shot_id)
    if shot is None:
        return None
    layers = await get_render_layers(shot.render_path)
    return ShotDetail(**shot.model_dump(), render_layers=layers)
