from typing import Any, Optional

import asyncio
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app.api.routes import verify_api_key
from app.config import load_settings
from app.models.tvbox_source import (
    TvboxFeedInfo,
    TvboxReorderItem,
    TvboxSourceCreate,
    TvboxSourceResponse,
    TvboxSourceTestResult,
    TvboxSourceUpdate,
)
from app.models.tvbox_test_report import TvboxTestReportResponse, TvboxTestReportSummary
from app.services.tvbox_report_service import get_latest_report, list_report_history
from app.services.tvbox_scheduler import tvbox_scheduler
from app.services.file_manager import get_public_base_url
from app.services.tvbox_service import tvbox_service
from app.tvbox_testing.spider_client import check_sidecar_health

router = APIRouter(tags=["tvbox"])


def _feed_public_allowed() -> bool:
    s = load_settings()
    tvbox = getattr(s, "tvbox", None)
    if tvbox is not None:
        return bool(getattr(tvbox, "public_feed", True))
    return True


def _feed_title() -> str:
    s = load_settings()
    tvbox = getattr(s, "tvbox", None)
    if tvbox is not None:
        return getattr(tvbox, "feed_title", "") or "Family Media Center TVBox 多合一"
    return "Family Media Center TVBox 多合一"


def _feed_url(request: Request) -> str:
    base = str(request.base_url).rstrip("/")
    return f"{base}/api/v1/tvbox/feed.json"


@router.get("/api/v1/tvbox/sources", response_model=list[TvboxSourceResponse])
async def list_tvbox_sources() -> list[TvboxSourceResponse]:
    return await tvbox_service.list_sources()


@router.get("/api/v1/tvbox/feed-info", response_model=TvboxFeedInfo)
async def get_tvbox_feed_info(request: Request) -> TvboxFeedInfo:
    sources = await tvbox_service.list_sources()
    enabled = [s for s in sources if s.enabled]
    return TvboxFeedInfo(
        feed_url=_feed_url(request),
        source_count=len(sources),
        enabled_count=len(enabled),
        title=_feed_title(),
    )


@router.get("/api/v1/tvbox/feed.json")
async def get_tvbox_feed(request: Request) -> JSONResponse:
    if not _feed_public_allowed():
        verify_api_key(request)
    config = await tvbox_service.build_merged_config(
        public_base=get_public_base_url(str(request.base_url).rstrip("/"))
    )
    return JSONResponse(content=config)


@router.post(
    "/api/v1/tvbox/sources",
    response_model=TvboxSourceResponse,
    dependencies=[Depends(verify_api_key)],
)
async def create_tvbox_source(data: TvboxSourceCreate) -> TvboxSourceResponse:
    try:
        return await tvbox_service.create_source(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put(
    "/api/v1/tvbox/sources/{source_id}",
    response_model=TvboxSourceResponse,
    dependencies=[Depends(verify_api_key)],
)
async def update_tvbox_source(source_id: int, data: TvboxSourceUpdate) -> TvboxSourceResponse:
    try:
        return await tvbox_service.update_source(source_id, data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete(
    "/api/v1/tvbox/sources/{source_id}",
    dependencies=[Depends(verify_api_key)],
)
async def delete_tvbox_source(source_id: int) -> dict[str, Any]:
    try:
        await tvbox_service.delete_source(source_id)
        return {"ok": True, "id": source_id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/api/v1/tvbox/sources/reorder",
    response_model=list[TvboxSourceResponse],
    dependencies=[Depends(verify_api_key)],
)
async def reorder_tvbox_sources(items: list[TvboxReorderItem]) -> list[TvboxSourceResponse]:
    pairs = [(item.id, item.sort_order) for item in items]
    return await tvbox_service.reorder_sources(pairs)


@router.post(
    "/api/v1/tvbox/sources/{source_id}/test",
    response_model=TvboxSourceTestResult,
    dependencies=[Depends(verify_api_key)],
)
async def test_tvbox_source(
    source_id: int,
    mode: str = Query("quick", pattern="^(quick|full)$"),
) -> TvboxSourceTestResult:
    try:
        return await tvbox_service.test_source(source_id, mode=mode)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/api/v1/tvbox/sources/test-all",
    response_model=list[TvboxSourceTestResult],
    dependencies=[Depends(verify_api_key)],
)
async def test_all_tvbox_sources(
    mode: str = Query("quick", pattern="^(quick|full)$"),
) -> list[TvboxSourceTestResult]:
    return await tvbox_service.test_all_sources(mode=mode)


@router.get(
    "/api/v1/tvbox/sources/{source_id}/reports/latest",
    response_model=TvboxTestReportResponse,
)
async def get_latest_tvbox_report(source_id: int) -> TvboxTestReportResponse:
    report = await get_latest_report(source_id)
    if not report:
        raise HTTPException(status_code=404, detail="暂无测试报告")
    return report


@router.get("/api/v1/tvbox/sidecar/status")
async def get_tvbox_sidecar_status() -> dict[str, Any]:
    return await check_sidecar_health()


@router.get(
    "/api/v1/tvbox/sources/{source_id}/reports/history",
    response_model=list[TvboxTestReportSummary],
)
async def get_tvbox_report_history(
    source_id: int,
    limit: int = Query(30, ge=1, le=100),
) -> list[TvboxTestReportSummary]:
    return await list_report_history(source_id, limit=limit)


@router.get("/api/v1/tvbox/schedule/status")
async def get_tvbox_schedule_status() -> dict[str, Any]:
    payload = tvbox_scheduler.status()
    payload["sidecar"] = await check_sidecar_health()
    return payload


@router.post(
    "/api/v1/tvbox/schedule/run",
    dependencies=[Depends(verify_api_key)],
)
async def run_tvbox_scheduled_test(
    mode: Optional[str] = Query(None, pattern="^(quick|full)$"),
) -> dict[str, Any]:
    if tvbox_scheduler.status()["running"]:
        raise HTTPException(status_code=409, detail="定时测试正在运行中")
    asyncio.create_task(tvbox_scheduler.run_once(mode_override=mode))
    return {"ok": True, "message": "已触发后台测试"}


@router.get("/api/v1/tvbox/overview")
async def get_tvbox_overview() -> dict[str, Any]:
    sources = await tvbox_service.list_sources()
    tested = [s for s in sources if s.last_test_score is not None]
    scores = [s.last_test_score for s in tested if s.last_test_score is not None]
    grades: dict[str, int] = {}
    for item in tested:
        g = item.last_test_grade or "unknown"
        grades[g] = grades.get(g, 0) + 1
    availability: dict[str, int] = {}
    for item in sources:
        avail = (item.last_test_detail or {}).get("summary", {}).get("availability")
        if not avail:
            if item.last_test_ok is True:
                avail = "full"
            elif item.last_test_ok is False:
                avail = "failed"
            else:
                avail = "unknown"
        availability[avail] = availability.get(avail, 0) + 1
    return {
        "source_count": len(sources),
        "enabled_count": sum(1 for s in sources if s.enabled),
        "tested_count": len(tested),
        "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
        "min_score": min(scores) if scores else None,
        "max_score": max(scores) if scores else None,
        "grades": grades,
        "availability": availability,
        "schedule": tvbox_scheduler.status(),
    }
