"""
Settings for the Shot Manager pipeline backend.

All values come from environment variables or a .env file.
No hardcoded paths, server addresses, or studio-specific values.

SHOT_PATTERN and SHOT_ID_FORMAT / SHOT_DIR_FORMAT are the key customisation
points for studios with naming conventions other than ep/sq/sh.

  SHOT_PATTERN must use named groups — e.g. (?P<ep>\\d+) — because
  SHOT_ID_FORMAT and SHOT_DIR_FORMAT reference those group names as
  format placeholders.  The three group names that map to "episode",
  "sequence", and "shot" in ShotModel are declared via the SHOT_EP_GROUP,
  SHOT_SQ_GROUP, and SHOT_SH_GROUP settings; they default to "ep", "sq",
  "sh" to match the default pattern.
"""
from __future__ import annotations

import re
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        # Don't raise on extra env vars — studios may have unrelated vars set.
        extra="ignore",
    )

    # -----------------------------------------------------------------------
    # Server paths — required in production, empty by default for dev/test
    # -----------------------------------------------------------------------
    RENDER_PATH: str = ""   # Root of the render tree, e.g. //server/prj/render
    COMP_PATH: str = ""     # Root of the comp tree,   e.g. //server/prj/comp
    CACHE_PATH_NEW: str = "" # Current cache / alembic location for cameras
    CACHE_PATH_OLD: str = "" # Legacy cache location (fallback camera lookup)

    # -----------------------------------------------------------------------
    # Shot naming convention
    # -----------------------------------------------------------------------

    # SHOT_PATTERN is applied to paths *relative to RENDER_PATH* using
    # re.fullmatch.  It must use named groups so that SHOT_ID_FORMAT and
    # SHOT_DIR_FORMAT can reference them.
    #
    # Default matches:  ep01/sq05/sh001
    SHOT_PATTERN: str = r"ep(?P<ep>\d+)[/\\]sq(?P<sq>\d+)[/\\]sh(?P<sh>\d+)"

    # SHOT_ID_FORMAT builds the shot's canonical identifier from the matched
    # named groups.  Placeholders must match the group names in SHOT_PATTERN.
    SHOT_ID_FORMAT: str = "ep{ep}_sq{sq}_sh{sh}"

    # SHOT_DIR_FORMAT builds the shot sub-path used when constructing comp /
    # precomp / camera paths from the matched named groups.
    SHOT_DIR_FORMAT: str = "ep{ep}/sq{sq}/sh{sh}"

    # Map named groups to the ShotModel fields episode / sequence / shot.
    # Change these if your pattern uses different group names.
    SHOT_EP_GROUP: str = "ep"
    SHOT_SQ_GROUP: str = "sq"
    SHOT_SH_GROUP: str = "sh"

    # How many directory levels below RENDER_PATH to scan.
    # Must equal the number of path components in SHOT_PATTERN (default: 3).
    SHOT_SCAN_DEPTH: int = 3

    # Name of the sub-directory inside each shot dir that holds render layers.
    SHOT_RENDER_SUBDIR: str = "render"

    # Camera file lookup inside the cache tree.
    SHOT_CAM_SUBDIR: str = "src"
    SHOT_CAM_FILENAME: str = "shot_camera.abc"

    # -----------------------------------------------------------------------
    # Cerebro
    # -----------------------------------------------------------------------
    CEREBRO_SERVER: str = ""
    CEREBRO_CARGADOR_ADDRESS: str = ""
    CEREBRO_CARGADOR_NATIVE_PORT: int = 7779
    CEREBRO_CARGADOR_HTTP_PORT: int = 7780

    # Path to a JSON file containing {"name": "...", "pass": "..."}.
    CEREBRO_ACCOUNT_PATH: str = ""

    # Template for constructing the Cerebro task URL from shot groups.
    # Use Python format-string syntax with the same named groups as
    # SHOT_PATTERN, converted to int for zero-padded formatting.
    # Example: "/{project}/Prod/ep{ep:02d}/sq{sq:02d}/sh{sh:03d}/compos"
    CEREBRO_TASK_URL_TEMPLATE: str = ""

    # -----------------------------------------------------------------------
    # Nuke script templates
    # -----------------------------------------------------------------------
    TEMPLATE_COMP_PATH: str = ""    # Path to a .nk template for comp scripts
    TEMPLATE_PRECOMP_PATH: str = "" # Path to a .nk template for precomp scripts

    # -----------------------------------------------------------------------
    # Thumbnail generation
    # -----------------------------------------------------------------------
    # Primary seek position (seconds from start).  Used as-is when the video
    # is longer than this value.
    THUMBNAIL_SEEK_TIME: float = 0.5
    # Fallback seek when the video is shorter than THUMBNAIL_SEEK_TIME.
    THUMBNAIL_FALLBACK_SEEK: float = 0.1

    # -----------------------------------------------------------------------
    # Shot-list cache
    # -----------------------------------------------------------------------
    SHOT_CACHE_TTL_HOURS: int = 1
    # Directory where the shot-list JSON cache is written.
    # Defaults to /tmp when empty.
    SHOT_CACHE_PATH: str = ""

    # -----------------------------------------------------------------------
    # Validators
    # -----------------------------------------------------------------------

    @field_validator("SHOT_PATTERN")
    @classmethod
    def _validate_shot_pattern(cls, v: str) -> str:
        try:
            compiled = re.compile(v)
        except re.error as exc:
            raise ValueError(f"SHOT_PATTERN is not a valid regex: {exc}") from exc
        if not compiled.groupindex:
            raise ValueError(
                "SHOT_PATTERN must use named groups (e.g. (?P<ep>\\d+)) "
                "so that SHOT_ID_FORMAT and SHOT_DIR_FORMAT can reference them."
            )
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton Settings instance (cached after first call)."""
    return Settings()
