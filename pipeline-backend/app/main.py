import os

from fastapi import FastAPI

from .config import get_settings
from .models.schemas import HealthResponse
from .routers import cerebro, scripts, shots, thumbnails
from .services import cerebro_service

app = FastAPI(
    title="Shot Manager Pipeline Backend",
    description="FastAPI backend for the Nuke Shot Manager panel.",
    version="2.0.0",
)

app.include_router(shots.router)
app.include_router(thumbnails.router)
app.include_router(scripts.router)
app.include_router(cerebro.router)


@app.get("/health", response_model=HealthResponse)
async def health():
    settings = get_settings()

    render_ok = bool(settings.RENDER_PATH and os.path.isdir(settings.RENDER_PATH))
    cerebro_ok = await cerebro_service.health_check()

    overall = "ok" if (render_ok and cerebro_ok) else "degraded"
    detail = None
    if not render_ok:
        detail = f"RENDER_PATH not reachable: {settings.RENDER_PATH!r}"
    elif not cerebro_ok:
        detail = "Cerebro unavailable (py_cerebro not installed or connection failed)"

    return HealthResponse(
        status=overall,
        render_path_ok=render_ok,
        cerebro_ok=cerebro_ok,
        detail=detail,
    )
