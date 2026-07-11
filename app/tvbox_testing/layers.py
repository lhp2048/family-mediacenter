"""Layer runners for TVBox testing."""

from __future__ import annotations

from typing import Any, Optional

import httpx

from app.tvbox_testing.config_parse import (
    is_live_url,
    parse_tvbox_body,
    summarize_tvbox_config,
    validate_config_content,
)
from app.tvbox_testing.http_client import FetchResult, fetch_url
from app.tvbox_testing.types import layer_result


def run_l1_from_fetch(fetch: FetchResult) -> dict[str, Any]:
    status: str
    score = 0
    if fetch.ok:
        status = "pass"
        score = 15
        if fetch.latency_ms > 5000:
            score = 10
        msg = fetch.message
        if fetch.redirect_count:
            msg = f"{msg} · 重定向 {fetch.redirect_count} 次"
    else:
        status = "fail"
        msg = fetch.message
    return layer_result(
        "L1",
        status,  # type: ignore[arg-type]
        message=msg,
        score=score,
        detail=fetch.to_summary(),
    )


async def run_l2_from_fetch(
    fetch: FetchResult,
    url: str,
) -> tuple[dict[str, Any], Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    """Returns (layer_result, config_dict, config_summary)."""
    if not fetch.ok or not fetch.body:
        return (
            layer_result("L2", "fail", message="L1 未通过，跳过格式检查", score=0),
            None,
            None,
        )

    path = url.lower().split("?", 1)[0]
    if is_live_url(url) or "mpegurl" in fetch.content_type.lower():
        if fetch.body.lstrip().startswith("#EXTM3U"):
            summary = {"format": "live_m3u", "type": "lives", "valid_json": False}
            return (
                layer_result("L2", "pass", message="M3U 直播格式", score=15, detail=summary),
                None,
                summary,
            )
        if path.endswith(".txt"):
            rows = sum(
                1
                for line in fetch.body.splitlines()
                if line.strip() and not line.startswith("#") and "," in line
            )
            if rows > 0:
                summary = {"format": "live_txt", "type": "lives", "channel_count": rows}
                return (
                    layer_result("L2", "pass", message=f"TXT 直播 {rows} 行", score=15, detail=summary),
                    None,
                    summary,
                )
        return layer_result("L2", "fail", message="直播格式无效", score=0), None, None

    data, parse_format = parse_tvbox_body(fetch.body)
    if data is None:
        preview = fetch.body.strip()[:80].replace("\n", " ")
        return (
            layer_result(
                "L2",
                "fail",
                message=f"无法解析配置（{parse_format}）",
                score=0,
                detail={"parse_format": parse_format, "preview": preview},
            ),
            None,
            None,
        )

    if not isinstance(data, dict):
        return layer_result("L2", "fail", message="根节点不是 JSON 对象", score=0), None, None

    summary = summarize_tvbox_config(data)
    summary["parse_format"] = parse_format
    ok, msg = validate_config_content(data, summary)
    if not ok:
        return (
            layer_result("L2", "fail", message=msg, score=5, detail=summary),
            data,
            summary,
        )

    return (
        layer_result("L2", "pass", message=msg, score=15, detail=summary),
        data,
        summary,
    )


async def run_l7_live(
    config: dict[str, Any] | None,
    fetch: FetchResult,
    url: str,
    *,
    client: httpx.AsyncClient,
    timeout: float,
    max_body: int,
    sample_channels: int = 3,
) -> dict[str, Any]:
    if fetch.body.lstrip().startswith("#EXTM3U") or url.lower().endswith((".m3u", ".m3u8")):
        return layer_result("L7", "pass", message="M3U 源格式有效", score=5)

    if not config:
        return layer_result("L7", "skip", message="无 lives 配置", score=0)

    channel_urls: list[str] = []
    for group in config.get("lives") or []:
        if not isinstance(group, dict):
            continue
        group_url = group.get("url")
        if isinstance(group_url, str) and group_url.strip().startswith("http"):
            channel_urls.append(group_url.strip())
        for ch in group.get("channels") or []:
            if isinstance(ch, dict):
                u = ch.get("url")
                if isinstance(u, str) and u.startswith("http"):
                    channel_urls.append(u.strip())
            elif isinstance(ch, str) and ch.startswith("http"):
                channel_urls.append(ch.strip())

    if not channel_urls:
        return layer_result("L7", "skip", message="无直播频道 URL", score=0)

    sample = channel_urls[: max(1, sample_channels)]
    ok_n = 0
    failed: list[dict[str, str]] = []
    for ch_url in sample:
        result = await fetch_url(
            ch_url, client=client, timeout=timeout, max_body=max_body
        )
        if result.ok:
            ok_n += 1
        else:
            failed.append({"url": ch_url[:80], "message": result.message})

    if ok_n == 0:
        return layer_result(
            "L7",
            "fail",
            message=f"直播频道探测失败 0/{len(sample)}",
            score=0,
            detail={"sampled": len(sample), "total": len(channel_urls), "failed": failed},
        )
    if ok_n < len(sample):
        return layer_result(
            "L7",
            "partial",
            message=f"部分直播频道可用 {ok_n}/{len(sample)}",
            score=3,
            detail={"sampled": len(sample), "ok": ok_n, "failed": failed},
        )
    return layer_result(
        "L7",
        "pass",
        message=f"直播频道可用 {ok_n}/{len(sample)}",
        score=5,
        detail={"sampled": len(sample), "total": len(channel_urls)},
    )


def run_l6_metrics(fetch: FetchResult, layers: list[dict[str, Any]]) -> dict[str, Any]:
    timeouts = sum(1 for layer in layers if "超时" in layer.get("message", ""))
    fails = sum(1 for layer in layers if layer.get("status") == "fail")
    score = 5
    if fetch.latency_ms > 8000:
        score = 1
    elif fetch.latency_ms > 3000:
        score = 3
    if timeouts or fails > 2:
        score = max(0, score - 2)
    return layer_result(
        "L6",
        "pass" if score >= 3 else "partial",
        message=f"延迟 {fetch.latency_ms}ms · 失败层 {fails}",
        score=score,
        detail={
            "latency_ms": fetch.latency_ms,
            "redirect_count": fetch.redirect_count,
            "failed_layers": fails,
        },
    )
