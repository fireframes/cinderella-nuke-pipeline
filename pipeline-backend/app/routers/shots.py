from typing import List, Optional

from fastapi import APIRouter, Query

from ..models.schemas import ScanResponse, ShotDetail, ShotModel
from ..services import shot_scanner

router = APIRouter(prefix="/shots", tags=["shots"])


@router.get("", response_model=List[ShotModel])
async def list_shots(
    ep: Optional[str] = Query(None, description="Filter by episode number, e.g. 01"),
    sq: Optional[str] = Query(None, description="Filter by sequence number, e.g. 05"),
):
    shots = await shot_scanner.scan_shots()
    if ep:
        shots = [s for s in shots if s.episode == ep]
    if sq:
        shots = [s for s in shots if s.sequence == sq]
    return shots


@router.get("/{shot_id}", response_model=ShotDetail)
async def get_shot(shot_id: str):
    from fastapi import HTTPException

    detail = await shot_scanner.get_shot_detail(shot_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Shot not found: {shot_id}")
    return detail


@router.post("/scan", response_model=ScanResponse)
async def force_scan():
    shots = await shot_scanner.scan_shots(force=True)
    return ScanResponse(count=len(shots), from_cache=False)
