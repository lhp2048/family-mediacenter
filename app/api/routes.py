from typing import Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from app.config import AppSettings, load_settings, save_settings
from app.models.pagination import DEFAULT_PAGE_SIZE, PaginatedResponse
from app.models.task import SettingsUpdate, TaskCreate, TaskResponse
from app.services.engine_status import (
    get_all_engine_status,
    get_engine_status,
    get_system_summary,
    status_to_dict,
)
from app.services.datacenter_integration import (
    list_home_card_registry,
    register_home_card,
    unregister_home_card,
)
from app.services.task_manager import task_manager
from app.utils.download_log import read_download_log

router = APIRouter(prefix="/api/v1", tags=["api"])


def verify_api_key(request: Request) -> None:
    s = load_settings()
    api_key = s.server.api_key
    if api_key:
        header = request.headers.get("X-API-Key", "")
        if header != api_key:
            raise HTTPException(status_code=401, detail="Invalid API key")


@router.post("/downloads", response_model=TaskResponse, dependencies=[Depends(verify_api_key)])
async def create_download(data: TaskCreate) -> TaskResponse:
    try:
        return await task_manager.create_task(data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tasks", dependencies=[Depends(verify_api_key)])
async def list_tasks(
    status: Optional[str] = Query(None),
    tab: Optional[str] = Query(None),
    page: Optional[int] = Query(None, ge=1),
    page_size: Optional[int] = Query(None, ge=1, le=100),
) -> Union[list[TaskResponse], PaginatedResponse[TaskResponse]]:
    if page is not None:
        return await task_manager.list_tasks(
            status=status,
            tab=tab,
            page=page,
            page_size=page_size or DEFAULT_PAGE_SIZE,
        )
    result = await task_manager.list_tasks(status=status, tab=tab)
    if isinstance(result, PaginatedResponse):
        return result.items
    return result


@router.get("/tasks/counts", dependencies=[Depends(verify_api_key)])
async def task_counts() -> dict:
    return await task_manager.get_task_counts()


@router.delete("/tasks/{task_id}", dependencies=[Depends(verify_api_key)])
async def delete_task(
    task_id: int,
    delete_file: bool = Query(False),
) -> dict:
    try:
        await task_manager.delete_task(task_id, delete_file=delete_file)
        return {"ok": True, "id": task_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/tasks/{task_id}", response_model=TaskResponse, dependencies=[Depends(verify_api_key)])
async def get_task(task_id: int) -> TaskResponse:
    try:
        return await task_manager.get_task(task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/tasks/{task_id}/log", dependencies=[Depends(verify_api_key)])
async def get_task_log(task_id: int) -> PlainTextResponse:
    try:
        await task_manager.get_task(task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    content = read_download_log(task_id)
    if content is None:
        raise HTTPException(status_code=404, detail="Download log not found")
    return PlainTextResponse(
        content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'inline; filename="download_{task_id}.log"'},
    )


@router.post(
    "/tasks/{task_id}/pause",
    response_model=TaskResponse,
    dependencies=[Depends(verify_api_key)],
)
async def pause_task(task_id: int) -> TaskResponse:
    try:
        return await task_manager.pause_task(task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/tasks/{task_id}/cancel",
    response_model=TaskResponse,
    dependencies=[Depends(verify_api_key)],
)
async def cancel_task(task_id: int) -> TaskResponse:
    try:
        return await task_manager.cancel_task(task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/settings", dependencies=[Depends(verify_api_key)])
async def get_settings() -> dict:
    s = load_settings()
    return {
        "server": s.server.model_dump(),
        "download": s.download.model_dump(),
        "files": s.files.model_dump(),
        "webdav": s.webdav.model_dump(),
        "materials": s.materials.model_dump(),
        "integration": s.integration.model_dump(),
        "tvbox": s.tvbox.model_dump(),
        "engines": {
            "ytdlp_path": s.engines.ytdlp_path,
            "ffmpeg_path": s.engines.ffmpeg_path,
            "ytdlp": s.engines.ytdlp.model_dump(),
            "aria2": s.engines.aria2.model_dump(),
            "alist": s.engines.alist.model_dump(),
        },
    }


@router.put("/settings", dependencies=[Depends(verify_api_key)])
async def update_settings(data: SettingsUpdate) -> dict:
    s = load_settings()
    if data.server:
        for k, v in data.server.items():
            if hasattr(s.server, k):
                setattr(s.server, k, v)
    if data.download:
        for k, v in data.download.items():
            if hasattr(s.download, k):
                setattr(s.download, k, v)
    if data.files:
        for k, v in data.files.items():
            if hasattr(s.files, k):
                setattr(s.files, k, v)
    if data.webdav:
        for k, v in data.webdav.items():
            if hasattr(s.webdav, k):
                setattr(s.webdav, k, v)
    if data.materials:
        for k, v in data.materials.items():
            if hasattr(s.materials, k):
                setattr(s.materials, k, v)
    if data.integration:
        from app.services.datacenter_integration import _strip_integration

        for k, v in data.integration.items():
            if k == "home_cards" and isinstance(v, list):
                from app.config import IntegrationHomeCardSettings

                s.integration.home_cards = [
                    IntegrationHomeCardSettings(**item)
                    if isinstance(item, dict)
                    else item
                    for item in v
                ]
                continue
            if hasattr(s.integration, k):
                setattr(s.integration, k, v)
        _strip_integration(s.integration)
    if data.tvbox:
        for k, v in data.tvbox.items():
            if hasattr(s.tvbox, k):
                setattr(s.tvbox, k, v)
    if data.engines:
        if "ytdlp_path" in data.engines:
            s.engines.ytdlp_path = data.engines["ytdlp_path"]
        if "ffmpeg_path" in data.engines:
            s.engines.ffmpeg_path = data.engines["ffmpeg_path"]
        if "ytdlp" in data.engines and isinstance(data.engines["ytdlp"], dict):
            for k, v in data.engines["ytdlp"].items():
                if hasattr(s.engines.ytdlp, k):
                    setattr(s.engines.ytdlp, k, v)
        if "aria2" in data.engines:
            for k, v in data.engines["aria2"].items():
                if hasattr(s.engines.aria2, k):
                    if k == "runtime":
                        from app.services.engine_status import normalize_runtime

                        v = normalize_runtime(str(v or "local"))
                    setattr(s.engines.aria2, k, v)
        if "alist" in data.engines:
            for k, v in data.engines["alist"].items():
                if hasattr(s.engines.alist, k):
                    if k == "runtime":
                        from app.services.engine_status import normalize_runtime

                        v = normalize_runtime(str(v or "local"))
                    setattr(s.engines.alist, k, v)
    save_settings(s)
    from app import config as config_module

    config_module.settings = load_settings()
    return await get_settings()


@router.get("/integration/home-cards", dependencies=[Depends(verify_api_key)])
async def integration_list_home_cards() -> dict:
    s = load_settings()
    result = await list_home_card_registry(s.integration)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "查询失败")
    return result


@router.post(
    "/integration/home-cards/{card_id}/register",
    dependencies=[Depends(verify_api_key)],
)
async def integration_register_home_card(card_id: str) -> dict:
    s = load_settings()
    result = await register_home_card(s.integration, card_id)
    if not result.get("ok"):
        raise HTTPException(
            status_code=400,
            detail=result.get("error") or "注册失败",
        )
    return result


@router.post(
    "/integration/home-cards/{card_id}/unregister",
    dependencies=[Depends(verify_api_key)],
)
async def integration_unregister_home_card(card_id: str) -> dict:
    s = load_settings()
    result = await unregister_home_card(s.integration, card_id)
    if not result.get("ok"):
        raise HTTPException(
            status_code=400,
            detail=result.get("error") or "注销失败",
        )
    return result


@router.get("/engines", dependencies=[Depends(verify_api_key)])
async def list_engines() -> dict:
    return await get_system_summary()


@router.get("/engines/{name}", dependencies=[Depends(verify_api_key)])
async def get_engine(name: str) -> dict:
    info = await get_engine_status(name)
    if not info:
        raise HTTPException(status_code=404, detail=f"Unknown engine: {name}")
    return status_to_dict(info)


@router.post("/engines/{name}/test", dependencies=[Depends(verify_api_key)])
async def test_engine(name: str) -> dict:
    info = await get_engine_status(name)
    if not info:
        raise HTTPException(status_code=404, detail=f"Unknown engine: {name}")
    return status_to_dict(info)


class EngineActionRequest(BaseModel):
    action: str
    password: Optional[str] = None


@router.post("/engines/{name}/actions", dependencies=[Depends(verify_api_key)])
async def engine_action(name: str, data: EngineActionRequest) -> dict:
    from app.services.engine_lifecycle import lifecycle_service

    try:
        job = await lifecycle_service.start_action(
            name, data.action, password=data.password or ""
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return job.to_dict()


@router.get("/engines/actions/{job_id}", dependencies=[Depends(verify_api_key)])
async def engine_action_job(job_id: str) -> dict:
    from app.services.engine_lifecycle import lifecycle_service

    job = lifecycle_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job.to_dict()
