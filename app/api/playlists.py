from typing import Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app.api.routes import verify_api_key
from app.models.pagination import DEFAULT_PAGE_SIZE, PaginatedResponse
from app.models.playlist import (
    PlaylistAutoplayUpdate,
    PlaylistCreate,
    PlaylistItemBulkDelete,
    PlaylistItemCreate,
    PlaylistItemReorder,
    PlaylistItemResponse,
    PlaylistProgressUpdate,
    PlaylistReloadResult,
    PlaylistRenameReplaceRequest,
    PlaylistRenameReplaceResult,
    PlaylistResponse,
    PlaylistShareResponse,
    WatchPlaylistResponse,
    WatchProgress,
)
from app.services.file_manager import get_public_base_url
from app.services.playlist_service import playlist_service

router = APIRouter(tags=["playlists"])


def _public_base(request: Request) -> str:
    return get_public_base_url(str(request.base_url).rstrip("/"))


@router.get("/api/v1/playlists", response_model=list[PlaylistResponse])
async def list_playlists(request: Request) -> list[PlaylistResponse]:
    return await playlist_service.list_playlists(_public_base(request))


@router.get("/api/v1/playlists/default", response_model=PlaylistResponse)
async def get_default_playlist(request: Request) -> PlaylistResponse:
    return await playlist_service.get_default_playlist(_public_base(request))


@router.get(
    "/api/v1/playlists/default/items",
    response_model=list[PlaylistItemResponse],
)
async def list_default_items(
    request: Request,
    probe: bool = Query(True, description="为 false 时不访问磁盘，大小和是否存在由 /files/info 补齐"),
) -> list[PlaylistItemResponse]:
    default = await playlist_service.get_default_playlist()
    return await playlist_service.list_items(default.id, _public_base(request), probe=probe)


@router.post(
    "/api/v1/playlists/default/reload",
    response_model=PlaylistReloadResult,
    dependencies=[Depends(verify_api_key)],
)
async def reload_default_playlist() -> PlaylistReloadResult:
    try:
        default = await playlist_service.get_default_playlist()
        return await playlist_service.reload_playlist_from_disk(default.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/api/v1/playlists/{playlist_id}", response_model=PlaylistResponse)
async def get_playlist(request: Request, playlist_id: int) -> PlaylistResponse:
    playlist = await playlist_service.get_playlist(playlist_id, _public_base(request))
    if not playlist:
        raise HTTPException(status_code=404, detail="播放列表不存在")
    return playlist


@router.get(
    "/api/v1/playlists/{playlist_id}/live.m3u",
    response_class=PlainTextResponse,
)
async def get_playlist_live_m3u(request: Request, playlist_id: int) -> PlainTextResponse:
    try:
        body = await playlist_service.build_live_m3u(
            playlist_id, _public_base(request)
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return PlainTextResponse(
        content=body,
        media_type="application/vnd.apple.mpegurl",
    )


@router.get(
    "/api/v1/playlists/{playlist_id}/items",
)
async def list_playlist_items(
    request: Request,
    playlist_id: int,
    page: Optional[int] = Query(None, ge=1),
    page_size: Optional[int] = Query(None, ge=1, le=100),
    probe: bool = Query(True, description="为 false 时不访问磁盘，大小和是否存在由 /files/info 补齐"),
) -> Union[list[PlaylistItemResponse], PaginatedResponse[PlaylistItemResponse]]:
    try:
        return await playlist_service.list_items(
            playlist_id,
            _public_base(request),
            page=page,
            page_size=page_size,
            probe=probe,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put(
    "/api/v1/playlists/{playlist_id}/items/reorder",
    response_model=list[PlaylistItemResponse],
    dependencies=[Depends(verify_api_key)],
)
async def reorder_playlist_items(
    request: Request, playlist_id: int, items: list[PlaylistItemReorder]
) -> list[PlaylistItemResponse]:
    try:
        pairs = [(item.id, item.sort_order) for item in items]
        return await playlist_service.reorder_items(
            playlist_id, pairs, _public_base(request)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post(
    "/api/v1/playlists/{playlist_id}/share",
    response_model=PlaylistShareResponse,
    dependencies=[Depends(verify_api_key)],
)
async def enable_playlist_share(
    request: Request, playlist_id: int
) -> PlaylistShareResponse:
    try:
        return await playlist_service.enable_share(playlist_id, _public_base(request))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete(
    "/api/v1/playlists/{playlist_id}/share",
    response_model=PlaylistShareResponse,
    dependencies=[Depends(verify_api_key)],
)
async def disable_playlist_share(playlist_id: int) -> PlaylistShareResponse:
    try:
        return await playlist_service.disable_share(playlist_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post(
    "/api/v1/playlists/{playlist_id}/share/rotate",
    response_model=PlaylistShareResponse,
    dependencies=[Depends(verify_api_key)],
)
async def rotate_playlist_share(
    request: Request, playlist_id: int
) -> PlaylistShareResponse:
    try:
        return await playlist_service.rotate_share(playlist_id, _public_base(request))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete(
    "/api/v1/playlists/{playlist_id}/share/progress",
    response_model=PlaylistResponse,
    dependencies=[Depends(verify_api_key)],
)
async def clear_playlist_share_progress(
    request: Request, playlist_id: int
) -> PlaylistResponse:
    try:
        await playlist_service.clear_share_progress(playlist_id)
        playlist = await playlist_service.get_playlist(
            playlist_id, _public_base(request)
        )
        if not playlist:
            raise ValueError("播放列表不存在")
        return playlist
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.put(
    "/api/v1/playlists/{playlist_id}/share/autoplay",
    response_model=PlaylistResponse,
    dependencies=[Depends(verify_api_key)],
)
async def set_playlist_share_autoplay(
    request: Request, playlist_id: int, data: PlaylistAutoplayUpdate
) -> PlaylistResponse:
    try:
        return await playlist_service.set_share_autoplay(
            playlist_id, data.autoplay, _public_base(request)
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/api/v1/watch/{token}", response_model=WatchPlaylistResponse)
async def get_watch_playlist(request: Request, token: str) -> WatchPlaylistResponse:
    try:
        return await playlist_service.get_watch_payload(token, _public_base(request))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.put("/api/v1/watch/{token}/progress", response_model=WatchProgress)
async def put_watch_progress(token: str, data: PlaylistProgressUpdate) -> WatchProgress:
    try:
        return await playlist_service.update_watch_progress(
            token, data.item_id, data.position_sec
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.put("/api/v1/watch/{token}/autoplay")
async def put_watch_autoplay(token: str, data: PlaylistAutoplayUpdate) -> dict:
    try:
        autoplay = await playlist_service.update_watch_autoplay(token, data.autoplay)
        return {"autoplay": autoplay}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post(
    "/api/v1/playlists/{playlist_id}/reload",
    response_model=PlaylistReloadResult,
    dependencies=[Depends(verify_api_key)],
)
async def reload_playlist(playlist_id: int) -> PlaylistReloadResult:
    try:
        return await playlist_service.reload_playlist_from_disk(playlist_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/api/v1/media/files")
async def list_media_files(
    request: Request,
    page: Optional[int] = Query(None, ge=1),
    page_size: Optional[int] = Query(None, ge=1, le=100),
    probe: bool = Query(True, description="为 false 时只返回文件名，大小由 /files/info 补齐"),
) -> Union[list[PlaylistItemResponse], PaginatedResponse[PlaylistItemResponse]]:
    return await playlist_service.list_media_files(
        _public_base(request),
        page=page,
        page_size=page_size,
        probe=probe,
    )


@router.post(
    "/api/v1/playlists",
    response_model=PlaylistResponse,
    dependencies=[Depends(verify_api_key)],
)
async def create_playlist(request: Request, data: PlaylistCreate) -> PlaylistResponse:
    try:
        created = await playlist_service.create_playlist(data)
        return await playlist_service.get_playlist(created.id, _public_base(request)) or created
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete(
    "/api/v1/playlists/{playlist_id}",
    dependencies=[Depends(verify_api_key)],
)
async def delete_playlist(playlist_id: int) -> dict:
    try:
        await playlist_service.delete_playlist(playlist_id)
        return {"ok": True, "id": playlist_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/api/v1/playlists/{playlist_id}/rename-replace",
    response_model=PlaylistRenameReplaceResult,
    dependencies=[Depends(verify_api_key)],
)
async def rename_replace_playlist_files(
    playlist_id: int, data: PlaylistRenameReplaceRequest
) -> PlaylistRenameReplaceResult:
    try:
        return await playlist_service.rename_replace_in_playlist(
            playlist_id,
            find=data.find,
            replace=data.replace,
            dry_run=data.dry_run,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post(
    "/api/v1/playlists/{playlist_id}/items",
    response_model=PlaylistItemResponse,
    dependencies=[Depends(verify_api_key)],
)
async def add_playlist_item(
    request: Request, playlist_id: int, data: PlaylistItemCreate
) -> PlaylistItemResponse:
    try:
        return await playlist_service.add_item(
            playlist_id,
            rel_path=data.rel_path,
            task_id=data.task_id,
            public_base=_public_base(request),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/api/v1/playlists/{playlist_id}/items/bulk-delete",
    dependencies=[Depends(verify_api_key)],
)
async def bulk_delete_playlist_items(
    playlist_id: int, data: PlaylistItemBulkDelete
) -> dict:
    try:
        removed = await playlist_service.remove_items(playlist_id, data.item_ids)
        return {"ok": True, "removed": removed}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete(
    "/api/v1/playlists/{playlist_id}/items/{item_id}",
    dependencies=[Depends(verify_api_key)],
)
async def remove_playlist_item(playlist_id: int, item_id: int) -> dict:
    try:
        await playlist_service.remove_item(playlist_id, item_id)
        return {"ok": True, "id": item_id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
