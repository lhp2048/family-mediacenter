from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse

from app.api.routes import verify_api_key
from app.models.playlist import WatchPlaylistResponse
from app.models.share_watch import (
    ShareDeviceAccessUpdate,
    ShareDeviceResponse,
    ShareEyeCareResponse,
    ShareEyeCareStatusResponse,
    ShareEyeCareUpdate,
    ShareEyeDeviceStatus,
    ShareStatEvent,
    ShareStatsResponse,
)
from app.services.file_manager import get_public_base_url
from app.services.share_watch import VISITOR_COOKIE, VISIT_COOKIE, parse_stats_range, share_watch
from app.utils.mime import media_type_for_path

router = APIRouter(tags=["share-watch"])


def _client_ip(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return ""


def _secure(request: Request) -> bool:
    return request.url.scheme == "https"


def write_visitor_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        VISITOR_COOKIE,
        token,
        max_age=60 * 60 * 24 * 365,
        httponly=True,
        samesite="lax",
        secure=_secure(request),
        path="/",
    )


def write_visit_cookie(response: Response, request: Request, visit_id: int) -> None:
    response.set_cookie(
        VISIT_COOKIE,
        str(visit_id),
        httponly=True,
        samesite="lax",
        secure=_secure(request),
        path="/",
    )


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=403, detail=str(exc))
    message = str(exc)
    status = 400 if message in {"事件类型无效", "访问记录无效", "日期无效", "日期范围无效"} else 404
    return HTTPException(status_code=status, detail=message)


@router.get("/api/v1/share/stats", response_model=ShareStatsResponse, dependencies=[Depends(verify_api_key)])
async def get_share_stats(
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
) -> ShareStatsResponse:
    try:
        start, end = parse_stats_range(from_date, to_date)
        return await share_watch.query_stats(start, end)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.get(
    "/api/v1/share/eye-care",
    response_model=ShareEyeCareResponse,
    dependencies=[Depends(verify_api_key)],
)
async def get_share_eye_care() -> ShareEyeCareResponse:
    return await share_watch.get_eye_care()


@router.put(
    "/api/v1/share/eye-care",
    response_model=ShareEyeCareResponse,
    dependencies=[Depends(verify_api_key)],
)
async def set_share_eye_care(data: ShareEyeCareUpdate) -> ShareEyeCareResponse:
    return await share_watch.set_eye_care(data.enabled, data.play_minutes, data.rest_minutes)


@router.get(
    "/api/v1/share/eye-care/status",
    response_model=ShareEyeCareStatusResponse,
    dependencies=[Depends(verify_api_key)],
)
async def get_share_eye_care_status() -> ShareEyeCareStatusResponse:
    return await share_watch.eye_care_status()


@router.post(
    "/api/v1/share/eye-care/devices/{device_id}/reset",
    response_model=ShareEyeDeviceStatus,
    dependencies=[Depends(verify_api_key)],
)
async def reset_share_device_eye(device_id: int) -> ShareEyeDeviceStatus:
    try:
        return await share_watch.reset_device_eye(device_id)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.put(
    "/api/v1/share/devices/{device_id}",
    response_model=ShareDeviceResponse,
    dependencies=[Depends(verify_api_key)],
)
async def set_share_device_access(
    device_id: int, data: ShareDeviceAccessUpdate
) -> ShareDeviceResponse:
    try:
        return await share_watch.set_allowed(device_id, data.allowed)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.post("/api/v1/watch/{token}/stats")
async def post_watch_stats(request: Request, token: str, data: ShareStatEvent) -> dict:
    raw_visit = request.cookies.get(VISIT_COOKIE, "")
    try:
        visit_id = int(raw_visit)
    except ValueError:
        raise HTTPException(status_code=400, detail="访问记录无效") from None
    try:
        return await share_watch.record_event(
            token,
            request.cookies.get(VISITOR_COOKIE, ""),
            visit_id,
            data.type,
            data.item_id,
            data.delta_sec,
        )
    except (ValueError, PermissionError) as exc:
        raise _http_error(exc) from exc


@router.get("/api/v1/watch/{token}/media/{item_id}")
async def get_watch_media(request: Request, token: str, item_id: int) -> FileResponse:
    try:
        path = await share_watch.media_file(
            token, request.cookies.get(VISITOR_COOKIE, ""), item_id
        )
    except (ValueError, PermissionError) as exc:
        raise _http_error(exc) from exc
    return FileResponse(
        path=path,
        media_type=media_type_for_path(path),
        content_disposition_type="inline",
    )


async def prepare_watch_response(
    request: Request, response: Response, token: str
) -> WatchPlaylistResponse:
    try:
        payload, visitor = await share_watch.prepare_watch(
            token,
            request.cookies.get(VISITOR_COOKIE, ""),
            _client_ip(request),
            request.headers.get("user-agent", ""),
            get_public_base_url(str(request.base_url)),
        )
    except ValueError as exc:
        raise _http_error(exc) from exc
    write_visitor_cookie(response, request, visitor)
    return payload
