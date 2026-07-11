#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import base64
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import tvbox_service as mod  # noqa: E402
from app.tvbox_testing.config_parse import (  # noqa: E402
    extract_sub_urls,
    parse_tvbox_body,
    validate_config_content,
)
from app.services.playlist_m3u import playlist_live_m3u_url, render_live_m3u  # noqa: E402
from app.models.playlist import PlaylistItemResponse  # noqa: E402
from app.tvbox_testing.orchestrator import (  # noqa: E402
    _apply_child_probe_to_l2,
    _child_probe_result,
    _probe_sub_configs,
    _testing_config,
)
from app.tvbox_testing.layers import run_l2_from_fetch  # noqa: E402
from app.tvbox_testing.http_client import DEFAULT_HEADERS, FetchResult, fetch_url  # noqa: E402


def test_parsers() -> None:
    assert parse_tvbox_body('{"urls":["http://a"]}')[1] == "json"
    payload = base64.b64encode(json.dumps({"sites": [{"key": "a"}]}).encode()).decode()
    assert parse_tvbox_body(payload)[1] == "base64"
    assert parse_tvbox_body("12345678**" + payload)[1] == "base64_prefixed"
    assert extract_sub_urls({"urls": ["a", {"url": "b"}]}) == ["a", "b"]
    assert extract_sub_urls(
        {
            "storeHouse": [
                {"sourceName": "A", "sourceUrl": "https://a"},
                {"sourceName": "B", "sourceUrl": "https://b"},
            ]
        }
    ) == ["https://a", "https://b"]

    relaxed, fmt = parse_tvbox_body('{"key":爱迪V2,"type":3,"api":csp_Demo}')
    assert fmt == "json_relaxed"
    assert isinstance(relaxed, dict)
    assert relaxed["key"] == "爱迪V2"
    assert relaxed["api"] == "csp_Demo"

    trailing, fmt2 = parse_tvbox_body('{"sites":[],"spider":"x",}')
    assert fmt2 in ("json_relaxed", "json5", "json5_relaxed")
    assert isinstance(trailing, dict)

    commented, fmt3 = parse_tvbox_body(
        '{"sites":[// section\n{"key":"a","name":"test"},\n{"key":"b"}]}'
    )
    assert fmt3 == "json_relaxed"
    assert isinstance(commented, dict)
    assert len(commented["sites"]) == 2

    broken_str, fmt4 = parse_tvbox_body(
        '{"parses":[{"name":"x","ext":{"flag":["优\n酷","mgtv"]}}]}'
    )
    assert fmt4 == "json_relaxed"
    assert broken_str["parses"][0]["ext"]["flag"][0] == "优酷"

    print("parser tests ok")


def test_playlist_m3u() -> None:
    url = playlist_live_m3u_url(3, "http://192.168.1.10:18026")
    assert url.endswith("/api/v1/playlists/3/live.m3u")

    body = render_live_m3u(
        [
            PlaylistItemResponse(
                id=1,
                playlist_id=3,
                rel_path="a.mp4",
                title="测试 A",
                public_url="http://192.168.1.10:18026/files/a.mp4",
                exists=True,
            )
        ]
    )
    assert body.startswith("#EXTM3U")
    assert "测试 A" in body
    assert "files/a.mp4" in body
    print("playlist m3u tests ok")


def test_child_probe_scoring() -> None:
    l2 = {"layer": "L2", "status": "pass", "message": "可用", "score": 15}
    probe_all_fail = _child_probe_result(
        [{"url": "a", "ok": False}, {"url": "b", "ok": False}],
        total=5,
    )
    _apply_child_probe_to_l2(l2, probe_all_fail)
    assert l2["status"] == "partial"
    assert l2["score"] == 8
    assert "子源均不可用" in l2["message"]

    avail = availability_from_layers(
        [{"layer": "L1", "status": "pass"}, l2],
        child_probe=probe_all_fail,
    )
    assert avail == "partial"

    l2_ok = {"layer": "L2", "status": "pass", "message": "可用", "score": 15}
    probe_partial = _child_probe_result(
        [{"url": "a", "ok": True}, {"url": "b", "ok": False}],
        total=4,
    )
    _apply_child_probe_to_l2(l2_ok, probe_partial)
    assert l2_ok["status"] == "partial"
    assert "1/2" in l2_ok["message"]
    print("child probe scoring tests ok")


async def test_dc2_child_probe() -> None:
    import httpx

    url = "https://jihulab.com/ygbh1/box/-/raw/main/dcang/dc2.json"
    cfg = _testing_config()
    async with httpx.AsyncClient(
        timeout=cfg["timeout"],
        follow_redirects=True,
        headers=DEFAULT_HEADERS,
    ) as client:
        fetch = await fetch_url(url, client=client, timeout=cfg["timeout"])
        _, config, _ = await run_l2_from_fetch(fetch, url)
        assert isinstance(config, dict)
        probe = await _probe_sub_configs(
            config,
            client=client,
            cfg=cfg,
            max_probe=cfg["probe_children"],
        )
        assert probe["ok"] >= 1
        assert probe["probed"] > cfg["probe_children"]
        l2 = {"layer": "L2", "status": "pass", "message": "可用", "score": 15}
        _apply_child_probe_to_l2(l2, probe)
        assert l2["status"] == "partial"
        print(
            "dc2 child probe:",
            probe["ok"],
            "/",
            probe["probed"],
            "total",
            probe["total"],
        )


async def test_l2_live_m3u() -> None:
    fetch = FetchResult(
        ok=True,
        message="ok",
        url="http://x.m3u",
        body="#EXTM3U\n#EXTINF:-1,a\nhttp://x\n",
    )
    _, _, summary = await run_l2_from_fetch(fetch, "http://x.m3u")
    assert summary and summary.get("format") == "live_m3u"


async def main() -> None:
    test_parsers()
    test_playlist_m3u()
    test_child_probe_scoring()
    await test_l2_live_m3u()
    await test_dc2_child_probe()
    cfg = await mod.tvbox_service.build_merged_config(
        public_base="http://127.0.0.1:18026"
    )
    print("feed keys:", list(cfg.keys()))
    print("vod urls:", len(cfg.get("urls", [])))
    lives = cfg.get("lives", [])
    print("live groups:", len(lives), "channels:", len(lives[0]["channels"]) if lives else 0)

    t0 = time.perf_counter()
    results = await mod.tvbox_service.test_all_sources()
    ok = sum(1 for r in results if r.ok)
    print(f"tested {len(results)} in {time.perf_counter() - t0:.1f}s, ok={ok}")
    for r in results:
        flag = "OK" if r.ok else "FAIL"
        print(f"  [{flag}] {r.name}: {r.message}")


if __name__ == "__main__":
    asyncio.run(main())
