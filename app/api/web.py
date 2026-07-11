from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.models.pagination import DEFAULT_PAGE_SIZE
from app.product import get_product_version
from app.services.engine_status import get_all_engine_status, get_system_summary
from app.services.file_manager import get_public_base_url, list_directory
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
    listing = list_directory("", base, page=1, page_size=DEFAULT_PAGE_SIZE)
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
