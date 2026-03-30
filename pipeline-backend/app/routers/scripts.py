from fastapi import APIRouter

from ..models.schemas import ScriptResponse
from ..services import script_service

router = APIRouter(prefix="/shots", tags=["scripts"])


@router.post("/{shot_id}/comp-script", response_model=ScriptResponse)
async def create_comp_script(shot_id: str):
    return await script_service.create_comp_script(shot_id)


@router.post("/{shot_id}/precomp-script", response_model=ScriptResponse)
async def create_precomp_script(shot_id: str):
    return await script_service.create_precomp_script(shot_id)
