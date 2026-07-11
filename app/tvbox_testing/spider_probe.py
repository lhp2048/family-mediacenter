"""Spider site probing via Java Sidecar for L3–L5."""

from __future__ import annotations

from typing import Any, Optional

import httpx

from app.tvbox_testing.config_parse import site_label
from app.tvbox_testing.spider_client import probe_spider_site, sidecar_enabled


def _layer_to_probe_result(site: dict[str, Any], layer_key: str, layer: dict[str, Any]) -> dict[str, Any]:
    name = site_label(site)
    return {
        "site": name,
        "ok": bool(layer.get("ok")),
        "status": layer.get("status") or ("pass" if layer.get("ok") else "fail"),
        "message": f"{name} · {layer.get('message') or layer_key}",
        "score": int(layer.get("score") or 0),
        "sample_vod_id": layer.get("sample_vod_id"),
        "vod_id": layer.get("vod_id"),
        "play_preview": layer.get("play_preview"),
        "engine": "spider",
    }


def _unavailable_result(site: dict[str, Any], message: str) -> dict[str, Any]:
    name = site_label(site)
    return {
        "site": name,
        "ok": False,
        "status": "fail",
        "message": f"{name} · {message}",
        "score": 0,
        "engine": "spider",
    }


async def probe_spider_site_layers(
    site: dict[str, Any],
    *,
    spider_jar: str = "",
    keyword: str = "电影",
    timeout: float = 20.0,
    client: Optional[httpx.AsyncClient] = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if not sidecar_enabled():
        msg = "Sidecar 未配置或未启用"
        fail = _unavailable_result(site, msg)
        return fail, dict(fail), dict(fail)

    response = await probe_spider_site(
        site,
        spider_jar=spider_jar,
        keyword=keyword,
        timeout=timeout,
        client=client,
    )
    if not response.get("ok"):
        msg = str(response.get("error") or "Sidecar 探测失败")
        fail = _unavailable_result(site, msg)
        return fail, dict(fail), dict(fail)

    layers = response.get("layers") or {}
    l3 = _layer_to_probe_result(site, "L3", layers.get("l3") or {})
    l4 = _layer_to_probe_result(site, "L4", layers.get("l4") or {})
    l5 = _layer_to_probe_result(site, "L5", layers.get("l5") or {})
    return l3, l4, l5
