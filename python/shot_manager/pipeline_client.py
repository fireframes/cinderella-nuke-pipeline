"""
PipelineClient — thin HTTP wrapper around the Shot Manager backend API.

The panel instantiates this once and calls it everywhere it previously called
filesystem or tracker methods directly.  BASE_URL is read from the environment
variable PIPELINE_BASE_URL (default: http://localhost:8000) so a studio can
point all artists at a shared server without changing any code.

Error contract
--------------
Every method raises PipelineError on a non-2xx response or a connection
failure, with a human-readable message suitable for nuke.message().
The panel catches PipelineError and shows the message; it never sees raw
requests exceptions or HTTP status codes.

Return types
------------
Methods return plain dicts or lists of dicts (parsed JSON).  No Pydantic
models — this file has no dependency on the backend package.
"""
from __future__ import annotations

import os
from typing import Any, Optional

try:
    import requests
    from requests.exceptions import ConnectionError, RequestException, Timeout
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _base_url() -> str:
    """Read base URL from env, stripping any trailing slash."""
    return os.environ.get("PIPELINE_BASE_URL", "http://localhost:8000").rstrip("/")


DEFAULT_TIMEOUT = 10   # seconds for all requests


# ---------------------------------------------------------------------------
# Error type
# ---------------------------------------------------------------------------

class PipelineError(RuntimeError):
    """Raised by PipelineClient on any backend or network failure."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class PipelineClient:
    """HTTP client for the Shot Manager pipeline backend.

    Usage::

        client = PipelineClient()          # reads PIPELINE_BASE_URL from env
        client = PipelineClient("http://server:8000")  # explicit URL

        shots = client.get_shots()
        shot  = client.get_shot("ep01_sq05_sh001")
    """

    def __init__(self, base_url: Optional[str] = None) -> None:
        if not _REQUESTS_AVAILABLE:
            raise PipelineError(
                "The 'requests' library is not installed.  "
                "Add it to your Nuke Python environment."
            )
        self.base_url = (base_url or _base_url()).rstrip("/")
        self._session = requests.Session()

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _get(self, path: str, params: Optional[dict] = None) -> Any:
        return self._request("GET", path, params=params)

    def _post(self, path: str, json: Optional[dict] = None) -> Any:
        return self._request("POST", path, json=json)

    def _request(self, method: str, path: str, **kwargs) -> Any:
        url = f"{self.base_url}{path}"
        kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
        try:
            resp = self._session.request(method, url, **kwargs)
        except Timeout:
            raise PipelineError(
                f"Request timed out after {DEFAULT_TIMEOUT}s.\n"
                f"Is the pipeline server running at {self.base_url}?"
            )
        except ConnectionError:
            raise PipelineError(
                f"Cannot reach pipeline server at {self.base_url}.\n"
                "Check that the server is running and PIPELINE_BASE_URL is correct."
            )
        except RequestException as exc:
            raise PipelineError(f"Network error: {exc}") from exc

        if not resp.ok:
            # Try to pull a detail message from the JSON body.
            detail = _extract_detail(resp)
            raise PipelineError(
                f"Server returned {resp.status_code} for {method} {path}.\n{detail}"
            )

        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    # -----------------------------------------------------------------------
    # Shots
    # -----------------------------------------------------------------------

    def get_shots(
        self,
        ep: Optional[str] = None,
        sq: Optional[str] = None,
    ) -> list[dict]:
        """Return all shots, optionally filtered by episode and/or sequence."""
        params = {}
        if ep is not None:
            params["ep"] = ep
        if sq is not None:
            params["sq"] = sq
        return self._get("/shots", params=params or None) or []

    def get_shot(self, shot_id: str) -> dict:
        """Return full shot detail including render layers."""
        return self._get(f"/shots/{shot_id}")

    def scan_shots(self) -> dict:
        """Force a backend rescan and return {count, from_cache}."""
        return self._post("/shots/scan")

    # -----------------------------------------------------------------------
    # Thumbnails
    # -----------------------------------------------------------------------

    def get_thumbnail(self, shot_id: str) -> dict:
        """Return {path, shot_id, generated} for the shot's thumbnail.

        Blocks until ffmpeg finishes if the thumbnail does not yet exist.
        Raise PipelineError if no .mov is found or ffmpeg fails.
        """
        return self._get(f"/shots/{shot_id}/thumbnail")

    # -----------------------------------------------------------------------
    # Scripts
    # -----------------------------------------------------------------------

    def create_comp_script(self, shot_id: str) -> dict:
        """Create (or locate) a comp .nk for *shot_id*.  Returns {path, shot_id, created}."""
        return self._post(f"/shots/{shot_id}/comp-script")

    def create_precomp_script(self, shot_id: str) -> dict:
        """Create or increment a precomp .nk for *shot_id*.  Returns {path, shot_id, created}."""
        return self._post(f"/shots/{shot_id}/precomp-script")

    # -----------------------------------------------------------------------
    # Production tracker (ShotGrid, ftrack, etc.)
    # -----------------------------------------------------------------------

    def get_tracker_statuses(self) -> list[dict]:
        """Return all tracker statuses as [{id, name, color}, ...]."""
        return self._get("/tracker/statuses") or []

    def get_tracker_tasks(self, shot_id: str) -> list[dict]:
        """Return tracker tasks for *shot_id*."""
        return self._get(f"/tracker/shots/{shot_id}/tasks") or []

    def set_tracker_status(self, shot_id: str, task_id: str, status_id: str) -> None:
        """Set a task status in the production tracker."""
        self._post(
            f"/tracker/shots/{shot_id}/status",
            json={"task_id": task_id, "status_id": status_id},
        )

    def add_tracker_report(
        self,
        shot_id: str,
        task_id: str,
        message: str,
        preview_path: Optional[str] = None,
        scene_path: Optional[str] = None,
        work_time: Optional[int] = None,
    ) -> None:
        """Add a report (and optional attachments) to a tracker task."""
        body: dict[str, Any] = {"task_id": task_id, "message": message}
        if preview_path is not None:
            body["preview_path"] = preview_path
        if scene_path is not None:
            body["scene_path"] = scene_path
        if work_time is not None:
            body["work_time"] = work_time
        self._post(f"/tracker/shots/{shot_id}/report", json=body)

    # -----------------------------------------------------------------------
    # Health
    # -----------------------------------------------------------------------

    def health(self) -> dict:
        """Return {status, render_path_ok, tracker_ok, detail}."""
        return self._get("/health")

    def is_reachable(self) -> bool:
        """Return True if the backend responds to /health without error."""
        try:
            self.health()
            return True
        except PipelineError:
            return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_detail(resp) -> str:
    try:
        body = resp.json()
        if isinstance(body, dict):
            return body.get("detail", resp.text)
    except Exception:
        pass
    return resp.text[:300]
