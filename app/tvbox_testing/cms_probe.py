"""CMS (MacCMS / Apple CMS) probing for L3–L5 site tests."""

from __future__ import annotations

import json
import re
from typing import Any, Optional
from urllib.parse import quote, urlsplit, urlunsplit

import httpx

from app.tvbox_testing.config_parse import site_label
from app.tvbox_testing.http_client import fetch_url
from app.tvbox_testing.types import TestMode, layer_result

_CMS_HINTS = ("provide/vod", "api.php", "/vod/", "pro/vod", "vodapi")
_PLAY_URL_RE = re.compile(r"https?://[^\s#|$]+", re.I)


def classify_site(site: dict[str, Any]) -> str:
    """Return site kind: cms | spider | unknown."""
    api = str(site.get("api") or "").strip()
    site_type = site.get("type")

    if api.startswith(("csp_", "CSP_")):
        return "spider"
    if isinstance(site_type, int) and site_type in (3, 4):
        return "spider"

    if api.startswith("http"):
        lower = api.lower()
        if any(h in lower for h in _CMS_HINTS):
            return "cms"
        if site_type in (0, 1, None, "0", "1"):
            return "cms"
    return "unknown"


def normalize_api_base(api: str) -> str:
    api = api.strip()
    if not api.startswith("http"):
        return ""
    parts = urlsplit(api)
    path = parts.path or ""
    if "?" in api:
        path = path.split("?", 1)[0]
    if path and not path.endswith("/"):
        path = path + "/"
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def _cms_url(base: str, params: str) -> str:
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}{params}"


def cms_list_url(base: str) -> str:
    return _cms_url(base, "ac=list")


def cms_search_url(base: str, keyword: str) -> str:
    encoded = quote(keyword)
    return _cms_url(base, f"ac=detail&wd={encoded}")


def cms_detail_url(base: str, vod_id: str) -> str:
    return _cms_url(base, f"ac=detail&ids={quote(vod_id)}")


def parse_cms_json(body: str) -> tuple[Optional[Any], str]:
    text = body.strip().lstrip("\ufeff")
    if not text:
        return None, "empty"
    try:
        return json.loads(text), ""
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1]), ""
        except json.JSONDecodeError as exc:
            return None, str(exc)
    return None, "invalid json"


def cms_response_ok(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    code = data.get("code")
    if code is not None:
        try:
            if int(code) == 1:
                return True
        except (TypeError, ValueError):
            pass
    return bool(data.get("list") or data.get("class"))


def extract_list_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw = data.get("list")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def extract_vod_id(item: dict[str, Any]) -> Optional[str]:
    for key in ("vod_id", "id", "vodId"):
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def extract_play_signal(detail_item: dict[str, Any]) -> Optional[str]:
    for key in ("vod_play_url", "vod_play_from", "play_url", "url"):
        value = detail_item.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        if key == "vod_play_url" or _PLAY_URL_RE.search(text):
            return text[:200]
    return None


async def probe_site_l3(
    site: dict[str, Any],
    *,
    client: httpx.AsyncClient,
    timeout: float,
    max_body: int,
) -> dict[str, Any]:
    name = site_label(site)
    api = str(site.get("api") or "").strip()
    base = normalize_api_base(api)
    if not base:
        return {
            "site": name,
            "ok": False,
            "status": "fail",
            "message": "无效 CMS API",
            "score": 0,
        }

    url = cms_list_url(base)
    fetch = await fetch_url(url, client=client, timeout=timeout, max_body=max_body)
    if not fetch.ok:
        return {
            "site": name,
            "ok": False,
            "status": "fail",
            "message": fetch.message,
            "score": 0,
            "url": url[:120],
        }

    data, err = parse_cms_json(fetch.body)
    if data is None or not isinstance(data, dict):
        return {
            "site": name,
            "ok": False,
            "status": "fail",
            "message": f"分类响应非 JSON（{err}）",
            "score": 0,
            "url": url[:120],
        }

    if not cms_response_ok(data):
        return {
            "site": name,
            "ok": False,
            "status": "fail",
            "message": "分类接口返回异常",
            "score": 0,
            "url": url[:120],
        }

    classes = data.get("class")
    class_count = len(classes) if isinstance(classes, list) else 0
    items = extract_list_items(data)
    vod_id = extract_vod_id(items[0]) if items else None

    if class_count > 0:
        msg = f"{name} · 分类 {class_count} 个"
        score = 15
    elif items:
        msg = f"{name} · 列表 {len(items)} 条（无 class）"
        score = 12
    else:
        msg = f"{name} · 接口可达但列表为空"
        score = 8

    return {
        "site": name,
        "ok": True,
        "status": "pass" if score >= 12 else "partial",
        "message": msg,
        "score": score,
        "url": url[:120],
        "class_count": class_count,
        "list_count": len(items),
        "sample_vod_id": vod_id,
    }


async def probe_site_l4(
    site: dict[str, Any],
    *,
    client: httpx.AsyncClient,
    timeout: float,
    max_body: int,
    keyword: str,
    sample_vod_id: Optional[str] = None,
) -> dict[str, Any]:
    name = site_label(site)
    api = str(site.get("api") or "").strip()
    base = normalize_api_base(api)
    if not base:
        return {
            "site": name,
            "ok": False,
            "status": "fail",
            "message": "无效 CMS API",
            "score": 0,
        }

    url = cms_search_url(base, keyword)
    fetch = await fetch_url(url, client=client, timeout=timeout, max_body=max_body)
    if not fetch.ok:
        return {
            "site": name,
            "ok": False,
            "status": "fail",
            "message": f"搜索失败: {fetch.message}",
            "score": 0,
            "url": url[:120],
        }

    data, err = parse_cms_json(fetch.body)
    if data is None or not isinstance(data, dict):
        return {
            "site": name,
            "ok": False,
            "status": "fail",
            "message": f"搜索响应非 JSON（{err}）",
            "score": 0,
            "url": url[:120],
        }

    items = extract_list_items(data)
    if not items and not cms_response_ok(data):
        return {
            "site": name,
            "ok": False,
            "status": "fail",
            "message": "搜索无结果且接口异常",
            "score": 0,
            "url": url[:120],
        }

    vod_id = sample_vod_id
    for item in items:
        vod_id = extract_vod_id(item)
        if vod_id:
            break

    if items:
        msg = f"{name} · 搜索「{keyword}」{len(items)} 条"
        return {
            "site": name,
            "ok": True,
            "status": "pass",
            "message": msg,
            "score": 10,
            "url": url[:120],
            "result_count": len(items),
            "sample_vod_id": vod_id,
        }

    if sample_vod_id:
        return {
            "site": name,
            "ok": True,
            "status": "partial",
            "message": f"{name} · 搜索无结果，沿用列表样本",
            "score": 5,
            "url": url[:120],
            "sample_vod_id": sample_vod_id,
        }

    return {
        "site": name,
        "ok": False,
        "status": "fail",
        "message": f"{name} · 搜索「{keyword}」无结果",
        "score": 0,
        "url": url[:120],
    }


async def probe_site_l5(
    site: dict[str, Any],
    *,
    client: httpx.AsyncClient,
    timeout: float,
    max_body: int,
    vod_id: Optional[str],
) -> dict[str, Any]:
    name = site_label(site)
    if not vod_id:
        return {
            "site": name,
            "ok": False,
            "status": "fail",
            "message": f"{name} · 无可用 vod_id",
            "score": 0,
        }

    api = str(site.get("api") or "").strip()
    base = normalize_api_base(api)
    if not base:
        return {
            "site": name,
            "ok": False,
            "status": "fail",
            "message": "无效 CMS API",
            "score": 0,
        }

    url = cms_detail_url(base, vod_id)
    fetch = await fetch_url(url, client=client, timeout=timeout, max_body=max_body)
    if not fetch.ok:
        return {
            "site": name,
            "ok": False,
            "status": "fail",
            "message": f"详情失败: {fetch.message}",
            "score": 0,
            "url": url[:120],
            "vod_id": vod_id,
        }

    data, err = parse_cms_json(fetch.body)
    if data is None or not isinstance(data, dict):
        return {
            "site": name,
            "ok": False,
            "status": "fail",
            "message": f"详情响应非 JSON（{err}）",
            "score": 0,
            "url": url[:120],
            "vod_id": vod_id,
        }

    items = extract_list_items(data)
    detail_item = items[0] if items else data.get("vod") if isinstance(data.get("vod"), dict) else None
    if not isinstance(detail_item, dict):
        detail_item = data

    play_signal = extract_play_signal(detail_item) if isinstance(detail_item, dict) else None
    if play_signal:
        return {
            "site": name,
            "ok": True,
            "status": "pass",
            "message": f"{name} · 详情含播放地址",
            "score": 20,
            "url": url[:120],
            "vod_id": vod_id,
            "play_preview": play_signal[:80],
        }

    if cms_response_ok(data) and items:
        return {
            "site": name,
            "ok": True,
            "status": "partial",
            "message": f"{name} · 详情可达但无播放字段",
            "score": 8,
            "url": url[:120],
            "vod_id": vod_id,
        }

    return {
        "site": name,
        "ok": False,
        "status": "fail",
        "message": f"{name} · 详情无播放地址",
        "score": 0,
        "url": url[:120],
        "vod_id": vod_id,
    }


def _aggregate_layer(
    layer_id: str,
    *,
    max_score: int,
    results: list[dict[str, Any]],
    skip_message: str,
) -> dict[str, Any]:
    if not results:
        return layer_result(layer_id, "skip", message=skip_message, score=0)

    passed = [item for item in results if item.get("status") == "pass"]
    partial = [item for item in results if item.get("status") == "partial"]
    failed = [item for item in results if item.get("status") == "fail"]

    best_score = max(int(item.get("score") or 0) for item in results)
    score = min(max_score, best_score)

    if passed:
        status = "pass"
        if partial or failed:
            status = "partial"
            score = min(max_score, max(int(item.get("score") or 0) for item in passed + partial))
        names = ", ".join(item["site"] for item in passed[:2])
        extra = len(passed) - 2
        msg = f"{len(passed)}/{len(results)} 站点通过 · {names}"
        if extra > 0:
            msg += f" 等{len(passed)}个"
    elif partial:
        status = "partial"
        msg = f"{len(partial)}/{len(results)} 站点部分可用"
    else:
        status = "fail"
        msg = failed[0].get("message", "全部站点失败") if failed else "全部站点失败"

    return layer_result(
        layer_id,  # type: ignore[arg-type]
        status,  # type: ignore[arg-type]
        message=msg,
        score=score,
        detail={
            "tested": len(results),
            "passed": len(passed),
            "partial": len(partial),
            "failed_count": len(failed),
            "sites": results,
        },
    )


async def run_aggregated_cms_layers(
    sites: list[Any],
    *,
    client: httpx.AsyncClient,
    mode: TestMode,
    timeout: float,
    max_body: int,
    max_sites: int = 3,
    search_keyword: str = "电影",
    spider_jar: str = "",
    spider_timeout: float = 25.0,
) -> list[dict[str, Any]]:
    """Run L3–L5 against CMS and Spider sites; returns exactly 3 layer dicts."""
    if mode == TestMode.QUICK:
        return [
            layer_result("L3", "skip", message="quick 模式跳过分类测试", score=0),
            layer_result("L4", "skip", message="quick 模式跳过搜索测试", score=0),
            layer_result("L5", "skip", message="quick 模式跳过播放测试", score=0),
        ]

    cms_sites: list[dict[str, Any]] = []
    spider_sites: list[dict[str, Any]] = []
    for site in sites:
        if not isinstance(site, dict):
            continue
        kind = classify_site(site)
        if kind == "cms":
            cms_sites.append(site)
        elif kind == "spider":
            spider_sites.append(site)

    if not cms_sites and not spider_sites:
        return [
            layer_result("L3", "skip", message="无可测站点", score=0),
            layer_result("L4", "skip", message="无可测站点", score=0),
            layer_result("L5", "skip", message="无可测站点", score=0),
        ]

    l3_results: list[dict[str, Any]] = []
    l4_results: list[dict[str, Any]] = []
    l5_results: list[dict[str, Any]] = []

    cms_targets = cms_sites[: max(1, max_sites)] if cms_sites else []
    for site in cms_targets:
        l3 = await probe_site_l3(
            site, client=client, timeout=timeout, max_body=max_body
        )
        l3_results.append(l3)

        vod_id = l3.get("sample_vod_id")
        l4 = await probe_site_l4(
            site,
            client=client,
            timeout=timeout,
            max_body=max_body,
            keyword=search_keyword,
            sample_vod_id=vod_id,
        )
        l4_results.append(l4)

        play_id = l4.get("sample_vod_id") or vod_id
        l5 = await probe_site_l5(
            site,
            client=client,
            timeout=timeout,
            max_body=max_body,
            vod_id=play_id,
        )
        l5_results.append(l5)

    spider_targets = spider_sites[: max(1, max_sites)] if spider_sites else []
    if spider_targets:
        from app.tvbox_testing.spider_probe import probe_spider_site_layers

        for site in spider_targets:
            per_site_jar = str(site.get("spider") or spider_jar or "")
            l3, l4, l5 = await probe_spider_site_layers(
                site,
                spider_jar=per_site_jar,
                keyword=search_keyword,
                timeout=spider_timeout,
                client=client,
            )
            l3_results.append(l3)
            l4_results.append(l4)
            l5_results.append(l5)

    return [
        _aggregate_layer("L3", max_score=15, results=l3_results, skip_message="无站点"),
        _aggregate_layer("L4", max_score=10, results=l4_results, skip_message="无站点"),
        _aggregate_layer("L5", max_score=20, results=l5_results, skip_message="无站点"),
    ]
