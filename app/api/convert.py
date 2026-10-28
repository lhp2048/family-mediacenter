"""Manual ffmpeg compat convert API."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.routes import verify_api_key
from app.services.ffmpeg_convert import convert_service
from app.services.file_manager import get_public_base_url


router = APIRouter(prefix="/api/v1", tags=["convert"])


class ConvertRequest(BaseModel):
    rel_path: Optional[str] = None
    playlist_id: Optional[int] = None
    item_id: Optional[int] = Field(default=None, description="Playlist item id")


@router.post("/convert", dependencies=[Depends(verify_api_key)])
async def start_convert(data: ConvertRequest, request: Request) -> dict:
    try:
        job = await convert_service.start_job(
            rel_path=data.rel_path,
            playlist_id=data.playlist_id,
            item_id=data.item_id,
            public_base=get_public_base_url(str(request.base_url).rstrip("/")),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return job.to_dict()


@router.get("/convert/{job_id}", dependencies=[Depends(verify_api_key)])
async def get_convert_job(job_id: str) -> dict:
    job = convert_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="转码任务不存在")
    return job.to_dict()
