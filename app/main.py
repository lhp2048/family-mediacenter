import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.api.bilibili import router as bilibili_router
from app.api.materials import router as materials_router
from app.api.playlists import router as playlists_router
from app.api.convert import router as convert_router
from app.api.files import router as files_router
from app.api.home_cards import router as home_cards_router
from app.api.routes import router as api_router
from app.api.skills import router as skills_router
from app.api.tvbox import router as tvbox_router
from app.api.web import router as web_router
from app.config import settings
from app.db import init_db
from app.middleware.private_network_access import PrivateNetworkAccessMiddleware
from app.product import get_product_version
from app.services.playlist_service import playlist_service
from app.services.task_manager import task_manager
from app.services.tvbox_scheduler import tvbox_scheduler
from app.webdav_app import create_webdav_asgi_app, webdav_is_ready

WEB_DIR = Path(__file__).resolve().parent / "web"


class Utf8HTMLMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        if content_type.startswith("text/html") and "charset" not in content_type.lower():
            response.headers["content-type"] = "text/html; charset=utf-8"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await playlist_service.ensure_default_playlist()
    await playlist_service.sync_default_from_tasks()
    await task_manager.recover_on_startup()
    await task_manager.start_polling()
    await tvbox_scheduler.start()
    yield
    await tvbox_scheduler.stop()
    await task_manager.stop_polling()


app = FastAPI(
    title="Family Media Center",
    description="Local download service with yt-dlp, aria2, and Alist",
    version=get_product_version(),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # pdf.js cross-origin (App :18027 → mediacenter :18026) must read these headers
    # or it falls back to a single full-file GET before rendering.
    expose_headers=["Accept-Ranges", "Content-Length", "Content-Range"],
)
app.add_middleware(PrivateNetworkAccessMiddleware)
app.add_middleware(Utf8HTMLMiddleware)

app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")
app.include_router(files_router)
app.include_router(bilibili_router)
app.include_router(materials_router)
app.include_router(home_cards_router)
app.include_router(playlists_router)
app.include_router(convert_router)
app.include_router(tvbox_router)
app.include_router(api_router)
app.include_router(skills_router)
app.include_router(web_router)

# WebDAV mounts at process start; toggle requires service restart.
if webdav_is_ready(settings.webdav):
    app.mount("/dav", create_webdav_asgi_app(settings.webdav), name="webdav")


def run() -> None:
    uvicorn.run(
        "app.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=False,
        log_level="info",
        access_log=True,
    )


if __name__ == "__main__":
    run()
