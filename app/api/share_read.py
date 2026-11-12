from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.api.routes import verify_api_key
from app.api.share_watch import write_visitor_cookie
from app.models.share_read import ShareReadEvent, ShareReadStatsResponse
from app.services.share_read import READ_VISIT_COOKIE, share_read
from app.services.share_watch import VISITOR_COOKIE, parse_stats_range

router = APIRouter(tags=["share-read"])


def _client_ip(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return ""


def _secure(request: Request) -> bool:
    return request.url.scheme == "https"


def write_read_visit_cookie(response: Response, request: Request, visit_id: int) -> None:
    response.set_cookie(
        READ_VISIT_COOKIE,
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
    if message in {"事件类型无效", "访问记录无效", "日期无效", "日期范围无效"} or "超出" in message or "格式" in message:
        status = 400
    else:
        status = 404
    return HTTPException(status_code=status, detail=message)


@router.get(
    "/api/v1/share/read-stats",
    response_model=ShareReadStatsResponse,
    dependencies=[Depends(verify_api_key)],
)
async def get_share_read_stats(
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
) -> ShareReadStatsResponse:
    try:
        start, end = parse_stats_range(from_date, to_date)
        return await share_read.query_stats(start, end)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.post("/api/v1/share/read/{token}/stats")
async def post_read_stats(request: Request, token: str, data: ShareReadEvent) -> dict:
    chosen = data.visit_id
    if not chosen:
        raw_visit = request.cookies.get(READ_VISIT_COOKIE, "")
        try:
            chosen = int(raw_visit)
        except ValueError:
            raise HTTPException(status_code=400, detail="访问记录无效") from None
    try:
        return await share_read.record_event(
            token,
            request.cookies.get(VISITOR_COOKIE, ""),
            chosen,
            data.type,
            data.delta_sec,
        )
    except (ValueError, PermissionError) as exc:
        raise _http_error(exc) from exc
