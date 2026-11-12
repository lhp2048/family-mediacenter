from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.models.pagination import DEFAULT_PAGE_SIZE
from app.product import get_product_version
from app.services.engine_status import get_all_engine_status, get_system_summary
from app.services.file_manager import get_public_base_url, list_directory_async
from app.services.task_manager import task_manager

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))


def _format_filesize(value: int) -> str:
    if not value or value <= 0:
        return "-"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{value} B"


templates.env.filters["filesize"] = _format_filesize


def _share_closed(
    request: Request,
    title: str,
    message: str,
    name: str = "",
    status_code: int = 200,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "share_closed.html",
        {
            "settings": settings,
            "title": title,
            "message": message,
            "name": name,
        },
        status_code=status_code,
    )


def _share_denied(request: Request, visitor: str) -> HTMLResponse:
    from app.api.share_watch import write_visitor_cookie

    response = templates.TemplateResponse(
        request,
        "share_denied.html",
        {"settings": settings},
    )
    write_visitor_cookie(response, request, visitor)
    return response


async def _share_access(request: Request, token: str) -> tuple[str, bool]:
    from app.services.share_read import share_read
    from app.services.share_watch import VISITOR_COOKIE

    return await share_read.prepare_access(
        token,
        request.cookies.get(VISITOR_COOKIE, ""),
        request.client.host if request.client else "",
        request.headers.get("user-agent", ""),
    )

router = APIRouter(tags=["web"])


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    result = await task_manager.list_tasks(tab="active", page=1, page_size=DEFAULT_PAGE_SIZE)
    counts = await task_manager.get_task_counts()
    tasks = result.items if hasattr(result, "items") else result
    pagination = result if hasattr(result, "total") else None
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "tasks": tasks,
            "counts": counts,
            "tab": "active",
            "settings": settings,
            "page": pagination.page if pagination else 1,
            "page_size": pagination.page_size if pagination else DEFAULT_PAGE_SIZE,
            "total": pagination.total if pagination else len(tasks),
            "total_pages": pagination.total_pages if pagination else 1,
        },
    )


@router.get("/partials/tasks", response_class=HTMLResponse)
async def tasks_partial(
    request: Request,
    tab: str = Query("active"),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=100),
) -> HTMLResponse:
    result = await task_manager.list_tasks(tab=tab, page=page, page_size=page_size)
    return templates.TemplateResponse(
        request,
        "partials/task_table.html",
        {
            "tasks": result.items,
            "tab": tab,
            "page": result.page,
            "page_size": result.page_size,
            "total": result.total,
            "total_pages": result.total_pages,
        },
    )


@router.get("/partials/task-counts", response_class=HTMLResponse)
async def task_counts_partial(request: Request) -> HTMLResponse:
    counts = await task_manager.get_task_counts()
    return templates.TemplateResponse(
        request,
        "partials/task_tabs.html",
        {"counts": counts, "tab": request.query_params.get("tab", "active")},
    )


@router.get("/components", response_class=HTMLResponse)
async def components_page(request: Request) -> HTMLResponse:
    summary = await get_system_summary()
    engines = await get_all_engine_status()
    return templates.TemplateResponse(
        request,
        "components.html",
        {"summary": summary, "engines": engines, "settings": settings},
    )


@router.get("/partials/components", response_class=HTMLResponse)
async def components_partial(request: Request) -> HTMLResponse:
    engines = await get_all_engine_status()
    return templates.TemplateResponse(
        request,
        "partials/components_status.html",
        {"engines": engines},
    )



@router.get("/files", response_class=HTMLResponse)
async def files_page(request: Request) -> HTMLResponse:
    base = get_public_base_url(str(request.base_url).rstrip("/"))
    listing = await list_directory_async("", base, page=1, page_size=DEFAULT_PAGE_SIZE)
    listing_json = listing.model_dump_json()
    return templates.TemplateResponse(
        request,
        "files.html",
        {
            "listing": listing,
            "listing_json": listing_json,
            "settings": settings,
        },
    )


@router.get("/media", response_class=HTMLResponse)
async def media_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "media.html",
        {"settings": settings},
    )


@router.get("/watch/{token}", response_class=HTMLResponse)
async def watch_page(request: Request, token: str) -> HTMLResponse:
    from app.api.share_watch import write_visit_cookie, write_visitor_cookie
    from app.services.playlist_service import playlist_service
    from app.services.share_watch import VISITOR_COOKIE, share_watch

    page = await playlist_service.get_share_page(token)
    if not page:
        return _share_closed(
            request,
            "这个链接无效",
            "链接打不开，可能已经被换掉了。",
            status_code=404,
        )
    enabled, name = page
    if not enabled:
        return _share_closed(
            request,
            "这个分享已暂停",
            "暂时不能播放。需要的话，请让家人重新打开分享。",
            name=name,
        )
    try:
        visitor, visit_id = await share_watch.open_visit(
            token,
            request.cookies.get(VISITOR_COOKIE, ""),
            request.client.host if request.client else "",
            request.headers.get("user-agent", ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    response = templates.TemplateResponse(
        request,
        "watch.html",
        {
            "token": token,
            "playlist_name": name,
            "settings": settings,
        },
    )
    write_visitor_cookie(response, request, visitor)
    write_visit_cookie(response, request, visit_id)
    return response


@router.get("/shelf/{token}", response_class=HTMLResponse)
async def shelf_page(request: Request, token: str, path: str = Query("")) -> HTMLResponse:
    from app.api.share_watch import write_visitor_cookie
    from app.services.material_share import material_share_service

    try:
        visitor, allowed = await _share_access(request, token)
        if not allowed:
            return _share_denied(request, visitor)
        shelf = await material_share_service.list_shelf(token, path)
    except ValueError as exc:
        status = 400 if "超出" in str(exc) else 404
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    response = templates.TemplateResponse(
        request,
        "shelf.html",
        {"settings": settings, "token": token, "shelf": shelf},
    )
    write_visitor_cookie(response, request, visitor)
    return response


@router.get("/shelf/{token}/read", response_class=HTMLResponse)
async def shelf_read_page(request: Request, token: str, path: str = Query("")) -> HTMLResponse:
    from app.api.share_read import write_read_visit_cookie
    from app.api.share_watch import write_visitor_cookie
    from app.services.material_share import material_share_service
    from app.services.share_read import share_read
    from app.services.share_watch import VISITOR_COOKIE

    try:
        visitor, allowed = await _share_access(request, token)
        if not allowed:
            return _share_denied(request, visitor)
        file_info = await material_share_service.shelf_read_info(token, path)
        visitor, visit_id = await share_read.open_read(
            token,
            path,
            request.cookies.get(VISITOR_COOKIE, "") or visitor,
            request.client.host if request.client else "",
            request.headers.get("user-agent", ""),
        )
    except ValueError as exc:
        status = 400 if "超出" in str(exc) or "格式" in str(exc) else 404
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    response = templates.TemplateResponse(
        request,
        "shelf_read.html",
        {
            "settings": settings,
            "file_info": file_info,
            "back_href": file_info["back_href"],
            "read_stats": True,
            "read_stats_token": token,
            "read_stats_visit": visit_id,
        },
    )
    write_visitor_cookie(response, request, visitor)
    write_read_visit_cookie(response, request, visit_id)
    return response


@router.get("/book/{token}", response_class=HTMLResponse)
async def book_share_page(request: Request, token: str) -> HTMLResponse:
    from app.api.share_read import write_read_visit_cookie
    from app.api.share_watch import write_visitor_cookie
    from app.services.material_share import material_share_service
    from app.services.share_read import share_read
    from app.services.share_watch import VISITOR_COOKIE

    try:
        visitor, allowed = await _share_access(request, token)
        if not allowed:
            return _share_denied(request, visitor)
        book = await material_share_service.book_info(token)
        visitor, visit_id = await share_read.open_read(
            token,
            "",
            request.cookies.get(VISITOR_COOKIE, "") or visitor,
            request.client.host if request.client else "",
            request.headers.get("user-agent", ""),
        )
    except ValueError as exc:
        status = 400 if "超出" in str(exc) or "格式" in str(exc) else 404
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    response = templates.TemplateResponse(
        request,
        "materials_embed.html",
        {
            "settings": settings,
            "file_info": {
                "name": book.name,
                "kind": book.kind,
                "public_url": book.file_url,
            },
            "read_stats": True,
            "read_stats_token": token,
            "read_stats_visit": visit_id,
        },
    )
    write_visitor_cookie(response, request, visitor)
    write_read_visit_cookie(response, request, visit_id)
    return response


@router.get("/materials", response_class=HTMLResponse)
async def materials_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "materials.html",
        {"settings": settings},
    )


@router.get("/materials/embed", response_class=HTMLResponse)
async def materials_embed_page(
    request: Request,
    path: str = Query("", description="书库内文件 sub_path"),
) -> HTMLResponse:
    from app.services.material_service import resolve_material_file

    public_base = get_public_base_url(str(request.base_url).rstrip("/"))
    try:
        file_info = resolve_material_file(public_base, path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return templates.TemplateResponse(
        request,
        "materials_embed.html",
        {
            "settings": settings,
            "file_info": file_info,
        },
    )


@router.get("/tvbox", response_class=HTMLResponse)
async def tvbox_page(request: Request) -> HTMLResponse:
    base_url = str(request.base_url).rstrip("/")
    return templates.TemplateResponse(
        request,
        "tvbox.html",
        {
            "settings": settings,
            "feed_url": f"{base_url}/api/v1/tvbox/feed.json",
        },
    )


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request) -> HTMLResponse:
    base_url = str(request.base_url).rstrip("/")
    return templates.TemplateResponse(
        request,
        "settings.html",
        {"settings": settings, "base_url": base_url},
    )


@router.get("/health")
async def health() -> dict:
    summary = await get_system_summary()
    engines_map = {e["name"]: e["available"] for e in summary["engines"]}
    return {
        "status": "ok",
        "service": "family_mediacenter",
        "version": get_product_version(),
        "port": settings.server.port,
        "engines": engines_map,
        "engines_available": summary["engines_available"],
        "engines_total": summary["engines_total"],
    }
