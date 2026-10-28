from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import aria2p

from app.config import settings
from app.engines.base import DownloadEngine, EngineProgress


class Aria2Engine(DownloadEngine):
    name = "aria2"

    def _client(self) -> aria2p.API:
        aria_cfg = settings.engines.aria2
        return aria2p.API(
            aria2p.Client(
                host=self._parse_host(aria_cfg.rpc_url),
                port=self._parse_port(aria_cfg.rpc_url),
                secret=aria_cfg.secret or "",
            )
        )

    def _parse_host(self, rpc_url: str) -> str:
        # aria2p expects host WITH scheme, e.g. "http://127.0.0.1"
        raw = (rpc_url or "").strip().rstrip("/")
        if raw.endswith("/jsonrpc"):
            raw = raw[: -len("/jsonrpc")]
        parsed = urlparse(raw if "://" in raw else f"http://{raw}")
        scheme = parsed.scheme if parsed.scheme in ("http", "https") else "http"
        host = parsed.hostname or "127.0.0.1"
        return f"{scheme}://{host}"

    def _parse_port(self, rpc_url: str) -> int:
        raw = (rpc_url or "").strip().rstrip("/")
        if raw.endswith("/jsonrpc"):
            raw = raw[: -len("/jsonrpc")]
        parsed = urlparse(raw if "://" in raw else f"http://{raw}")
        return parsed.port or 6800

    async def is_available(self) -> bool:
        try:
            client = self._client()
            client.client.get_version()
            return True
        except Exception:
            return False

    async def start(
        self,
        task_id: int,
        url: str,
        output_dir: str,
        options: dict[str, Any],
    ) -> str:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        client = self._client()
        download = client.add_uris(
            uris=[url],
            options={
                "dir": output_dir,
                "out": f"task_{task_id}_{options.get('filename', '')}".rstrip("_"),
            },
        )
        return download.gid

    async def poll(self, engine_task_id: str, task_id: int) -> EngineProgress:
        prog = EngineProgress()
        if not engine_task_id:
            return prog
        try:
            client = self._client()
            download = client.get_download(engine_task_id)
            if download is None:
                prog.status = "failed"
                prog.error_message = "aria2 download not found"
                return prog
            prog.progress = download.progress
            prog.speed = f"{download.download_speed} B/s"
            if download.files:
                prog.file_path = download.files[0].path
                prog.file_size = download.files[0].length
                prog.title = Path(prog.file_path).name
            if download.is_complete:
                prog.status = "completed"
                prog.progress = 100.0
            elif download.has_failed:
                prog.status = "failed"
                prog.error_message = download.error_message or "aria2 download failed"
            elif download.is_active:
                prog.status = "running"
            elif download.is_waiting:
                prog.status = "pending"
            elif download.is_paused:
                prog.status = "paused"
        except Exception as e:
            prog.status = "failed"
            prog.error_message = str(e)
        return prog

    async def pause(self, engine_task_id: str, task_id: int) -> bool:
        try:
            client = self._client()
            client.pause_downloads([engine_task_id])
            return True
        except Exception:
            return False

    async def cancel(self, engine_task_id: str, task_id: int) -> bool:
        try:
            client = self._client()
            client.remove([engine_task_id])
            return True
        except Exception:
            return False
