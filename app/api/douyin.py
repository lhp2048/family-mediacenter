from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.routes import verify_api_key
from app.services.douyin_login import (
    cancel_qr_login,
    get_douyin_login_status,
    poll_qr_login,
    start_qr_login,
)

router = APIRouter(prefix="/api/v1/douyin", tags=["douyin"])


@router.get("/login/status", dependencies=[Depends(verify_api_key)])
async def douyin_login_status() -> dict:
    return get_douyin_login_status()


@router.post("/qr/start", dependencies=[Depends(verify_api_key)])
async def douyin_qr_start() -> dict:
    try:
        return await start_qr_login()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/qr/cancel", dependencies=[Depends(verify_api_key)])
async def douyin_qr_cancel(session_id: str = Query(..., min_length=8)) -> dict:
    return await cancel_qr_login(session_id)


@router.get("/qr/poll", dependencies=[Depends(verify_api_key)])
async def douyin_qr_poll(session_id: str = Query(..., min_length=8)) -> dict:
    try:
        return await poll_qr_login(session_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
