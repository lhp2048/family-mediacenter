from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.routes import verify_api_key
from app.services.bilibili_login import (
    get_bilibili_login_status,
    poll_qr_login,
    start_qr_login,
)

router = APIRouter(prefix="/api/v1/bilibili", tags=["bilibili"])


@router.get("/login/status", dependencies=[Depends(verify_api_key)])
async def bilibili_login_status() -> dict:
    return get_bilibili_login_status()


@router.post("/qr/start", dependencies=[Depends(verify_api_key)])
async def bilibili_qr_start() -> dict:
    try:
        return await start_qr_login()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/qr/poll", dependencies=[Depends(verify_api_key)])
async def bilibili_qr_poll(session_id: str = Query(..., min_length=8)) -> dict:
    try:
        return await poll_qr_login(session_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
