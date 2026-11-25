from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field

from app.api.routes import verify_api_key
from app.models.pagination import DEFAULT_PAGE_SIZE
from app.models.task import TaskResponse
from app.services.file_manager import get_public_base_url
from app.services.material_library import (
    create_folder,
    delete_entry,
    import_ebook,
    move_entry,
    rename_entry,
    upload_ebook,
)
from app.services.material_service import browse_materials

router = APIRouter(tags=["materials"])


def _public_base(request: Request) -> str:
    return get_public_base_url(str(request.base_url).rstrip("/"))


def _http_error(exc: ValueError) -> HTTPException:
    message = str(exc)
    if "不存在" in message:
        status = 404
    elif "同名" in message or "已有分享" in message:
        status = 409
    else:
        status = 400
    return HTTPException(status_code=status, detail=message)


class MaterialImportRequest(BaseModel):
    url: str = Field(..., min_length=1)
    sub_path: str = ""
    filename: str = ""


class MaterialFolderRequest(BaseModel):
    path: str = Field(..., min_length=1)


class MaterialRenameRequest(BaseModel):
    path: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)


class MaterialMoveRequest(BaseModel):
    path: str = Field(..., min_length=1)
    dest: str = ""


@router.get("/api/v1/materials")
async def api_browse_materials(
    request: Request,
    path: str = Query("", description="相对书库根目录的路径"),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=100),
) -> dict:
    try:
        data = browse_materials(
            _public_base(request),
            sub_path=path,
            page=page,
            page_size=page_size,
        )
        return data.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post(
    "/api/v1/materials/import",
    response_model=TaskResponse,
    dependencies=[Depends(verify_api_key)],
)
async def api_import_material(data: MaterialImportRequest) -> TaskResponse:
    try:
        return await import_ebook(data.url, data.sub_path, data.filename)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/api/v1/materials/upload",
    dependencies=[Depends(verify_api_key)],
)
async def api_upload_material(
    file: UploadFile = File(...),
    sub_path: str = Form(""),
) -> dict:
    try:
        return await upload_ebook(sub_path, file.filename or "", file)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/api/v1/materials/folders",
    dependencies=[Depends(verify_api_key)],
)
async def api_create_material_folder(data: MaterialFolderRequest) -> dict:
    try:
        return create_folder(data.path)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/api/v1/materials/rename",
    dependencies=[Depends(verify_api_key)],
)
async def api_rename_material(data: MaterialRenameRequest) -> dict:
    try:
        return await rename_entry(data.path, data.name)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/api/v1/materials/move",
    dependencies=[Depends(verify_api_key)],
)
async def api_move_material(data: MaterialMoveRequest) -> dict:
    try:
        return await move_entry(data.path, data.dest)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.delete(
    "/api/v1/materials",
    dependencies=[Depends(verify_api_key)],
)
async def api_delete_material(path: str = Query(..., min_length=1)) -> dict:
    try:
        return await delete_entry(path)
    except ValueError as exc:
        raise _http_error(exc) from exc
