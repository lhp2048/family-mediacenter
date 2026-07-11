"""HTTP client for TVBox Java Spider Sidecar."""

from __future__ import annotations

from typing import Any, Optional

import httpx

from app.config import load_settings


def sidecar_base_url() -> str:
    tvbox = load_settings().tvbox
    url = (getattr(tvbox, "spider_sidecar_url", None) or "").strip()
    return url.rstrip("/")


def sidecar_enabled() -> bool:
    tvbox = load_settings().tvbox
    if not getattr(tvbox, "spider_sidecar_enabled", True):
        return False
    return bool(sidecar_base_url())


async def check_sidecar_health(
    *,
    client: Optional[httpx.AsyncClient] = None,
    timeout: float = 3.0,
) -> dict[str, Any]:
    base = sidecar_base_url()
    if not base:
        return {"ok": False, "message": "未配置 spider_sidecar_url"}
    url = f"{base}/health"

    async def _do(http: httpx.AsyncClient) -> dict[str, Any]:
        try:
            response = await http.get(url)
            if response.status_code != 200:
                return {"ok": False, "message": f"Sidecar HTTP {response.status_code}"}
            data = response.json()
            if not data.get("ok"):
                return {"ok": False, "message": "Sidecar 健康检查失败"}
            return {
                "ok": True,
                "message": "Sidecar 可用",
                "version": data.get("version"),
                "url": base,
            }
        except httpx.RequestError as exc:
            return {"ok": False, "message": f"Sidecar 未连接: {exc}"}

    if client is not None:
        return await _do(client)
    async with httpx.AsyncClient(timeout=timeout) as owned:
        return await _do(owned)


async def probe_spider_site(
    site: dict[str, Any],
    *,
    spider_jar: str = "",
    keyword: str = "电影",
    timeout: float = 20.0,
    client: Optional[httpx.AsyncClient] = None,
) -> dict[str, Any]:
    base = sidecar_base_url()
    if not base:
        return {"ok": False, "error": "未配置 Sidecar 地址"}

    payload = {
        "site": site,
        "spiderJar": spider_jar,
        "keyword": keyword,
        "timeoutSec": max(5, int(timeout)),
    }
    url = f"{base}/api/v1/probe"

    async def _do(http: httpx.AsyncClient) -> dict[str, Any]:
        try:
            response = await http.post(url, json=payload)
            data = response.json()
            if not isinstance(data, dict):
                return {"ok": False, "error": "Sidecar 响应无效"}
            return data
        except httpx.RequestError as exc:
            return {"ok": False, "error": f"Sidecar 请求失败: {exc}"}
        except ValueError:
            return {"ok": False, "error": "Sidecar 响应非 JSON"}

    if client is not None:
        return await _do(client)
    async with httpx.AsyncClient(timeout=timeout + 5) as owned:
        return await _do(owned)
