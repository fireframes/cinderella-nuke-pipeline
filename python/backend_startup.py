"""backend_startup.py

Starts the Shot Manager pipeline backend when Nuke launches.
Checks /health first — if the backend is already up, does nothing.
If not running, starts it via docker-compose up -d in a background thread
so Nuke startup is never blocked.
"""
from __future__ import annotations

import os
import subprocess
import threading
import urllib.request
import urllib.error

_BACKEND_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "pipeline-backend")
)
_HEALTH_URL = (
    os.environ.get("PIPELINE_BASE_URL", "http://localhost:8000").rstrip("/") + "/health"
)


def _is_running() -> bool:
    try:
        with urllib.request.urlopen(_HEALTH_URL, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def _start_docker() -> None:
    try:
        import nuke
        nuke.tprint("[pipeline] Backend not detected — starting via docker-compose...")
    except ImportError:
        print("[pipeline] Backend not detected — starting via docker-compose...")

    result = subprocess.run(
        ["docker-compose", "up", "-d"],
        cwd=_BACKEND_DIR,
        capture_output=True,
        text=True,
    )

    try:
        import nuke
        if result.returncode == 0:
            nuke.tprint("[pipeline] Backend started successfully.")
        else:
            nuke.tprint(
                f"[pipeline] docker-compose failed (exit {result.returncode}):\n"
                f"{result.stderr.strip()}"
            )
    except ImportError:
        if result.returncode != 0:
            print(f"[pipeline] docker-compose failed:\n{result.stderr.strip()}")


def ensure_backend_running() -> None:
    """Non-blocking: ping /health and start docker-compose if the backend is down."""

    def _check_and_start() -> None:
        if _is_running():
            try:
                import nuke
                nuke.tprint("[pipeline] Backend already running.")
            except ImportError:
                pass
            return
        _start_docker()

    t = threading.Thread(target=_check_and_start, daemon=True, name="pipeline-backend-start")
    t.start()
