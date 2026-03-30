from fastapi import APIRouter

from ..models.schemas import ThumbnailResponse
from ..services import thumbnail_service

router = APIRouter(prefix="/shots", tags=["thumbnails"])


@router.get("/{shot_id}/thumbnail", response_model=ThumbnailResponse)
async def get_thumbnail(shot_id: str):
    return await thumbnail_service.generate_thumbnail(shot_id)
