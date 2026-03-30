from typing import List

from fastapi import APIRouter

from ..models.schemas import (
    AddReportRequest,
    SetStatusRequest,
    StatusModel,
    TaskModel,
)
from ..services import cerebro_service

router = APIRouter(prefix="/cerebro", tags=["cerebro"])


@router.get("/statuses", response_model=List[StatusModel])
async def list_statuses():
    return await cerebro_service.get_statuses()


@router.get("/shots/{shot_id}/tasks", response_model=List[TaskModel])
async def list_tasks(shot_id: str):
    return await cerebro_service.get_tasks(shot_id)


@router.post("/shots/{shot_id}/status")
async def set_status(shot_id: str, body: SetStatusRequest):
    await cerebro_service.set_status(shot_id, body.task_id, body.status_id)
    return {"ok": True}


@router.post("/shots/{shot_id}/report")
async def add_report(shot_id: str, body: AddReportRequest):
    await cerebro_service.add_report(shot_id, body)
    return {"ok": True}
