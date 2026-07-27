from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse

from app.api.routes import verify_api_key
from app.config import load_settings
from app.models.pagination import DEFAULT_PAGE_SIZE
from app.services.file_manager import (
    delete_path,
    get_file_for_serve,
    get_public_base_url,
    list_directory,
    normalize_rel_path,
)
from app.services.playlist_service import playlist_service
from app.utils.mime import media_type_for_path

router = APIRouter(tags=["files"])


def _public_base(request: Request) -> str:
    return get_public_base_url(str(request.base_url).rstrip("/"))


@router.get("/api/v1/files", dependencies=[Depends(verify_api_key)])
async def api_list_files(
    request: Request,
    path: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=100),
) -> dict:
    try:
        data = list_directory(path, _public_base(request), page=page, page_size=page_size)
        return data.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/api/v1/files", dependencies=[Depends(verify_api_key)])
async def api_delete_file(path: str = Query(...)) -> dict:
    try:
        rel = normalize_rel_path(path)
        delete_path(path)
        if rel:
            await playlist_service.remove_items_by_rel_path(rel)
        return {"ok": True, "path": path}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _wants_download(download: Optional[str]) -> bool:
    if download is None:
        return False
    return download.strip().lower() in {"1", "true"}


@router.get("/files/{file_path:path}")
async def serve_public_file(
    request: Request,
    file_path: str,
    download: Optional[str] = Query(None),
) -> FileResponse:
    s = load_settings()
    if not s.files.public_access:
        verify_api_key(request)
    try:
        target = get_file_for_serve(file_path)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    if _wants_download(download):
        return FileResponse(
            path=target,
            media_type=media_type_for_path(target),
            filename=target.name,
            content_disposition_type="attachment",
        )
    return FileResponse(
        path=target,
        media_type=media_type_for_path(target),
        content_disposition_type="inline",
    )
