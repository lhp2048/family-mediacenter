from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse

from app.api.routes import verify_api_key
from app.models.material_share import (
    MaterialBookResponse,
    MaterialShareResponse,
    MaterialShareUpdate,
    MaterialShelfResponse,
)
from app.services.file_manager import get_public_base_url
from app.services.material_share import material_share_service
from app.utils.mime import media_type_for_path

router = APIRouter(tags=["material-share"])


def _public_base(request: Request) -> str:
    return get_public_base_url(str(request.base_url).rstrip("/"))


def _http_error(exc: ValueError) -> HTTPException:
    message = str(exc)
    status = 404 if "不存在" in message or "已停用" in message else 400
    return HTTPException(status_code=status, detail=message)


async def _require_reader(request: Request) -> None:
    from app.services.share_read import share_read
    from app.services.share_watch import VISITOR_COOKIE

    try:
        await share_read.assert_allowed(request.cookies.get(VISITOR_COOKIE, ""))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post(
    "/api/v1/materials/share",
    response_model=MaterialShareResponse,
    dependencies=[Depends(verify_api_key)],
)
async def enable_material_share(
    request: Request, data: MaterialShareUpdate
) -> MaterialShareResponse:
    try:
        return await material_share_service.enable(data.sub_path, _public_base(request))
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.delete(
    "/api/v1/materials/share",
    response_model=MaterialShareResponse,
    dependencies=[Depends(verify_api_key)],
)
async def disable_material_share(data: MaterialShareUpdate) -> MaterialShareResponse:
    try:
        return await material_share_service.disable(data.sub_path)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/api/v1/materials/share/rotate",
    response_model=MaterialShareResponse,
    dependencies=[Depends(verify_api_key)],
)
async def rotate_material_share(
    request: Request, data: MaterialShareUpdate
) -> MaterialShareResponse:
    try:
        return await material_share_service.rotate(data.sub_path, _public_base(request))
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.get(
    "/api/v1/materials/share",
    response_model=MaterialShareResponse,
    dependencies=[Depends(verify_api_key)],
)
async def material_share_status(
    request: Request, sub_path: str = Query("")
) -> MaterialShareResponse:
    return await material_share_service.status(sub_path, _public_base(request))


@router.get("/api/v1/shelf/{token}", response_model=MaterialShelfResponse)
async def get_shelf(
    request: Request, token: str, path: str = Query("")
) -> MaterialShelfResponse:
    await _require_reader(request)
    try:
        return await material_share_service.list_shelf(token, path)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.get("/api/v1/shelf/{token}/file")
async def get_shelf_file(request: Request, token: str, path: str = Query("")) -> FileResponse:
    await _require_reader(request)
    try:
        target = await material_share_service.open_file(token, path)
    except ValueError as exc:
        raise _http_error(exc) from exc
    return FileResponse(
        path=target,
        media_type=media_type_for_path(target),
        content_disposition_type="inline",
    )


@router.get("/api/v1/book/{token}", response_model=MaterialBookResponse)
async def get_book(request: Request, token: str) -> MaterialBookResponse:
    await _require_reader(request)
    try:
        return await material_share_service.book_info(token)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.get("/api/v1/book/{token}/file")
async def get_book_file(request: Request, token: str) -> FileResponse:
    await _require_reader(request)
    try:
        target = await material_share_service.open_file(token, "")
    except ValueError as exc:
        raise _http_error(exc) from exc
    return FileResponse(
        path=target,
        media_type=media_type_for_path(target),
        content_disposition_type="inline",
    )
