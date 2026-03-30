"""
Script creation service.

Handles creation of comp and precomp .nk scripts on the backend filesystem.
No Nuke runtime is required — scripts are created via file I/O:
  - Directory structure is created
  - Templates (if configured) are copied and patched with correct paths
  - Minimal stub .nk files are written when no template is available

The panel opens the returned path via nuke.scriptOpen().
"""
from __future__ import annotations

import asyncio
import os
import re
import shutil
from typing import Optional

from fastapi import HTTPException

from ..config import get_settings
from ..models.schemas import ScriptResponse, ShotModel
from .shot_scanner import get_render_layers, get_shot

# ---------------------------------------------------------------------------
# .nk file helpers
# ---------------------------------------------------------------------------

_MINIMAL_NKB = """\
Root {{
 name ""
 project_directory {project_directory}
}}
"""


def _write_minimal_nk(path: str, project_directory: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(_MINIMAL_NKB.format(project_directory=project_directory))


def _find_exr_sequence_for_layer(layer_path: str) -> Optional[tuple[str, int, int]]:
    """Return (nuke_format_path, first, last) for the EXR sequence in *layer_path*."""
    # Reuse the helper from shot_scanner to avoid duplication.
    from .shot_scanner import _find_exr_sequence  # local import to avoid cycles

    return _find_exr_sequence(layer_path)


def _patch_nk_for_precomp(
    content: str,
    layers_by_name: dict[str, str],   # base layer name → full layer dir path
    shot_id: str,
    precomp_dir: str,
) -> str:
    """Patch a .nk template for a specific shot.

    Read nodes whose ``file`` knob contains a known layer name have their path
    replaced with the actual EXR sequence for that layer (including first/last
    frame knobs).  Write node paths are redirected to the precomp output dirs.

    This is a line-by-line state-machine approach that handles the standard
    Nuke .nk text format; it does not require a Nuke runtime.
    """
    lines = content.splitlines(keepends=True)
    result: list[str] = []

    in_read = False
    in_write = False
    nesting = 0                          # tracks { } depth inside a node block
    pending_seq: Optional[tuple[str, int, int]] = None  # (path, first, last)

    for line in lines:
        stripped = line.strip()

        # --- Node block entry ---
        if re.match(r"^Read\s*\{", stripped):
            in_read = True
            in_write = False
            nesting = 1
            pending_seq = None
            result.append(line)
            continue

        if re.match(r"^Write\s*\{", stripped):
            in_write = True
            in_read = False
            nesting = 1
            result.append(line)
            continue

        # --- Nesting tracking ---
        opens = stripped.count("{")
        closes = stripped.count("}")
        if in_read or in_write:
            nesting += opens - closes
            if nesting <= 0:
                in_read = False
                in_write = False
                nesting = 0
                pending_seq = None
                result.append(line)
                continue

        # --- Read node patching ---
        if in_read and stripped.startswith("file "):
            current_path = stripped[5:].strip()
            matched_seq = None
            for layer_name, layer_dir in layers_by_name.items():
                if layer_name in current_path:
                    matched_seq = _find_exr_sequence_for_layer(layer_dir)
                    break
            if matched_seq:
                pending_seq = matched_seq
                indent = len(line) - len(line.lstrip())
                result.append(f"{' ' * indent}file {matched_seq[0]}\n")
            else:
                result.append(line)
            continue

        if in_read and pending_seq and stripped.startswith("first "):
            indent = len(line) - len(line.lstrip())
            result.append(f"{' ' * indent}first {pending_seq[1]}\n")
            continue

        if in_read and pending_seq and stripped.startswith("last "):
            indent = len(line) - len(line.lstrip())
            result.append(f"{' ' * indent}last {pending_seq[2]}\n")
            continue

        # --- Write node patching ---
        if in_write and stripped.startswith("file "):
            current_lower = stripped[5:].strip().lower()
            indent = len(line) - len(line.lstrip())
            precomp_fwd = precomp_dir.replace("\\", "/")
            if ".exr" in current_lower:
                new_path = f"{precomp_fwd}/exr/{shot_id}_precomp.%04d.exr"
            elif ".mov" in current_lower:
                new_path = f"{precomp_fwd}/mov/{shot_id}_precomp_v01.mov"
            else:
                result.append(line)
                continue
            result.append(f"{' ' * indent}file {new_path}\n")
            continue

        result.append(line)

    return "".join(result)


# ---------------------------------------------------------------------------
# Directory helpers
# ---------------------------------------------------------------------------

def _ensure_dirs(*paths: str) -> None:
    for p in paths:
        os.makedirs(p, exist_ok=True)


def _next_version(nk_dir: str, pattern: str) -> int:
    """Return the next version integer above the highest *_vNN* script in *nk_dir*."""
    if not os.path.isdir(nk_dir):
        return 1
    ver_re = re.compile(pattern)
    versions = [
        int(m.group(1))
        for f in os.listdir(nk_dir)
        if (m := ver_re.search(f))
    ]
    return max(versions, default=0) + 1


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _create_comp_script_sync(shot: ShotModel) -> ScriptResponse:
    settings = get_settings()

    nk_dir = f"{shot.comp_path}/nk"
    _ensure_dirs(nk_dir, f"{shot.comp_path}/exr", f"{shot.comp_path}/mov")

    script_name = f"{shot.shot_id}_v01.nk"
    script_path = os.path.join(nk_dir, script_name).replace("\\", "/")

    if os.path.exists(script_path):
        return ScriptResponse(path=script_path, shot_id=shot.shot_id, created=False)

    template = settings.TEMPLATE_COMP_PATH
    if template and os.path.exists(template):
        shutil.copy2(template, script_path)
    else:
        _write_minimal_nk(script_path, shot.comp_path)

    return ScriptResponse(path=script_path, shot_id=shot.shot_id, created=True)


async def create_comp_script(shot_id: str) -> ScriptResponse:
    """Create a comp script for *shot_id* and return its path."""
    shot = await get_shot(shot_id)
    if shot is None:
        raise HTTPException(status_code=404, detail=f"Shot not found: {shot_id}")
    return await asyncio.to_thread(_create_comp_script_sync, shot)


def _create_precomp_script_sync(shot: ShotModel) -> ScriptResponse:
    settings = get_settings()

    precomp_nk_dir = f"{shot.precomp_path}/nk"
    _ensure_dirs(
        precomp_nk_dir,
        f"{shot.precomp_path}/exr",
        f"{shot.precomp_path}/mov",
    )

    # Determine version.
    existing = [f for f in os.listdir(precomp_nk_dir) if f.endswith(".nk")] if os.path.isdir(precomp_nk_dir) else []

    if existing:
        # Version increment: copy the latest script to a new version file.
        ver_re = re.compile(r"_v(\d+)\.nk$")
        latest = max(
            existing,
            key=lambda f: int(m.group(1)) if (m := ver_re.search(f)) else 0,
        )
        latest_ver = int(m.group(1)) if (m := ver_re.search(latest)) else 1
        new_ver = latest_ver + 1
        new_name = f"{shot.shot_id}_precomp_v{new_ver:02d}.nk"
        src = os.path.join(precomp_nk_dir, latest)
        dst = os.path.join(precomp_nk_dir, new_name).replace("\\", "/")
        shutil.copy2(src, dst)
        return ScriptResponse(path=dst, shot_id=shot.shot_id, created=True)

    # Initial creation (v01).
    script_name = f"{shot.shot_id}_precomp_v01.nk"
    script_path = os.path.join(precomp_nk_dir, script_name).replace("\\", "/")

    template = settings.TEMPLATE_PRECOMP_PATH
    if template and os.path.exists(template):
        with open(template, encoding="utf-8") as fh:
            content = fh.read()

        # Build layer name → dir map from the render path.
        from .shot_scanner import _get_render_layers_sync  # avoid module-level cycle

        layers = _get_render_layers_sync(shot.render_path)
        layers_by_name = {layer.name: layer.path for layer in layers}

        patched = _patch_nk_for_precomp(
            content,
            layers_by_name,
            shot.shot_id,
            shot.precomp_path,
        )
        with open(script_path, "w", encoding="utf-8") as fh:
            fh.write(patched)
    else:
        _write_minimal_nk(script_path, shot.precomp_path)

    return ScriptResponse(path=script_path, shot_id=shot.shot_id, created=True)


async def create_precomp_script(shot_id: str) -> ScriptResponse:
    """Create (or increment) a precomp script for *shot_id* and return its path."""
    shot = await get_shot(shot_id)
    if shot is None:
        raise HTTPException(status_code=404, detail=f"Shot not found: {shot_id}")
    return await asyncio.to_thread(_create_precomp_script_sync, shot)
