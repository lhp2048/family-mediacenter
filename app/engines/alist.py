from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.engines.aria2 import Aria2Engine
from app.engines.base import DownloadEngine, EngineProgress


class AlistEngine(DownloadEngine):
    name = "alist"
    _aria2 = Aria2Engine()
    _alist_tasks: dict[int, str] = {}

    async def is_available(self) -> bool:
        cfg = settings.engines.alist
        if not cfg.enabled or not cfg.url:
            return False
        try:
            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                r = await client.get(f"{cfg.url.rstrip('/')}/api/public/settings")
                return r.status_code == 200
        except Exception:
            return False

    def _headers(self) -> dict[str, str]:
        cfg = settings.engines.alist
        headers: dict[str, str] = {}
        if cfg.token:
            headers["Authorization"] = cfg.token
        return headers

    async def _api_post(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        cfg = settings.engines.alist
        url = f"{cfg.url.rstrip('/')}/api{path}"
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            r = await client.post(url, json=data, headers=self._headers())
            r.raise_for_status()
            body = r.json()
            if body.get("code") != 200:
                raise RuntimeError(body.get("message", "Alist API error"))
            return body.get("data", {})

    async def _resolve_share(self, share_url: str) -> list[dict[str, Any]]:
        parsed = urlparse(share_url)
        path_parts = [p for p in parsed.path.split("/") if p]
        if "s" in path_parts:
            idx = path_parts.index("s")
            if idx + 1 < len(path_parts):
                share_id = path_parts[idx + 1]
                pwd = ""
                if "d" in path_parts and idx + 2 < len(path_parts):
                    pwd = path_parts[idx + 2]
                data = await self._api_post(
                    "/fs/get",
                    {"path": f"/s/{share_id}", "password": pwd},
                )
                return data if isinstance(data, list) else [data]
        return []

    async def _get_download_url(self, path: str) -> str:
        data = await self._api_post("/fs/get", {"path": path})
        if isinstance(data, dict):
            raw = data.get("raw_url") or data.get("sign")
            if raw:
                return raw
            sign_data = await self._api_post("/fs/link", {"path": path})
            return sign_data.get("raw_url") or sign_data.get("url") or ""
        return ""

    async def start(
        self,
        task_id: int,
        url: str,
        output_dir: str,
        options: dict[str, Any],
    ) -> str:
        cfg = settings.engines.alist
        if not cfg.enabled:
            raise RuntimeError("Alist is not enabled in settings")

        download_url = url
        alist_path = options.get("alist_path")

        if url.startswith("alist://"):
            alist_path = url.replace("alist://", "", 1)
        elif "/s/" in url or "alist" in url.lower():
            items = await self._resolve_share(url)
            if items:
                first = items[0]
                alist_path = first.get("path") or first.get("name")

        if alist_path:
            download_url = await self._get_download_url(alist_path)
            if not download_url:
                raise RuntimeError(f"Failed to get download URL for Alist path: {alist_path}")

        if options.get("offline_to_alist"):
            data = await self._api_post(
                "/fs/other",
                {
                    "method": "offline_download",
                    "data": {
                        "path": options.get("alist_dest", "/"),
                        "urls": [download_url],
                    },
                },
            )
            task_id_str = str(data.get("id", task_id))
            self._alist_tasks[task_id] = task_id_str
            return f"alist:{task_id_str}"

        gid = await self._aria2.start(task_id, download_url, output_dir, options)
        return gid

    async def poll(self, engine_task_id: str, task_id: int) -> EngineProgress:
        if engine_task_id.startswith("alist:"):
            return await self._poll_alist_task(engine_task_id.replace("alist:", ""))
        return await self._aria2.poll(engine_task_id, task_id)

    async def _poll_alist_task(self, alist_task_id: str) -> EngineProgress:
        prog = EngineProgress(status="running")
        try:
            data = await self._api_post(
                "/admin/task/list",
                {"page": 1, "per_page": 100, "type": "offline_download"},
            )
            tasks = data.get("content", []) if isinstance(data, dict) else []
            for t in tasks:
                if str(t.get("id")) == alist_task_id:
                    state = t.get("state", "")
                    prog.progress = float(t.get("progress", 0))
                    if state in ("finished", "completed"):
                        prog.status = "completed"
                        prog.progress = 100.0
                    elif state in ("failed", "error"):
                        prog.status = "failed"
                        prog.error_message = t.get("error", "Alist offline task failed")
                    else:
                        prog.status = "running"
                    break
        except Exception as e:
            prog.status = "failed"
            prog.error_message = str(e)
        return prog

    async def pause(self, engine_task_id: str, task_id: int) -> bool:
        if engine_task_id.startswith("alist:"):
            return False
        return await self._aria2.pause(engine_task_id, task_id)

    async def cancel(self, engine_task_id: str, task_id: int) -> bool:
        if engine_task_id.startswith("alist:"):
            return False
        return await self._aria2.cancel(engine_task_id, task_id)
