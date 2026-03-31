import os

from fastapi import FastAPI

from .config import get_settings
from .models.schemas import HealthResponse
from .routers import scripts, shots, thumbnails, tracker
from .services import tracker_service

app = FastAPI(
    title="Shot Manager Pipeline Backend",
    description="FastAPI backend for the Nuke Shot Manager panel.",
    version="2.0.0",
)

app.include_router(shots.router)
app.include_router(thumbnails.router)
app.include_router(scripts.router)
app.include_router(tracker.router)


@app.get("/health", response_model=HealthResponse)
async def health():
    settings = get_settings()

    render_ok = bool(settings.RENDER_PATH and os.path.isdir(settings.RENDER_PATH))
    tracker_ok = await tracker_service.health_check()

    overall = "ok" if (render_ok and tracker_ok) else "degraded"
    detail = None
    if not render_ok:
        detail = f"RENDER_PATH not reachable: {settings.RENDER_PATH!r}"
    elif not tracker_ok:
        backend = settings.TRACKER_BACKEND or "none"
        detail = f"Production tracker unavailable (TRACKER_BACKEND={backend!r})"

    return HealthResponse(
        status=overall,
        render_path_ok=render_ok,
        tracker_ok=tracker_ok,
        detail=detail,
    )
