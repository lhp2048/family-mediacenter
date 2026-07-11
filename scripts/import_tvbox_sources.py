#!/usr/bin/env python3
"""One-shot import TVBox sources from preset list."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.tvbox_source import TvboxSourceCreate, TvboxSourceUpdate  # noqa: E402
from app.services.tvbox_service import tvbox_service  # noqa: E402

SOURCES = [
    {"type": 0, "name": "月光宝盒官方", "url": "https://jihulab.com/ygbh1/box/-/raw/main/月光宝盒"},
    {"type": 0, "name": "月光宝盒多仓", "url": "https://jihulab.com/ygbh1/box/-/raw/main/dcang/dc2.json"},
    {"type": 0, "name": "月光宝盒单仓", "url": "https://jihulab.com/ygbh1/box/-/raw/main/ys.json"},
    {"type": 0, "name": "饭太硬", "url": "http://www.饭太硬.com/tv"},
    {"type": 0, "name": "肥猫", "url": "http://肥猫.com"},
    {"type": 0, "name": "王二小放牛娃", "url": "https://9280.kstore.vip/newwex.json"},
    {"type": 0, "name": "俊于", "url": "http://home.jundie.top:81/top98.json"},
    {"type": 0, "name": "巧技", "url": "http://cdn.qiaoji8.com/tvbox.json"},
    {"type": 0, "name": "小盒子", "url": "http://xhztv.top/xhz"},
    {"type": 0, "name": "南风综合多仓", "url": "https://gh-proxy.net/https://raw.githubusercontent.com/yoursmile66/TVBox/refs/heads/main/XC.json"},
    {"type": 0, "name": "匿名多仓", "url": "https://12586.kstore.space/123.json"},
    {"type": 0, "name": "潇洒多仓", "url": "https://9877.kstore.space/AnotherDS/api.json"},
    {"type": 0, "name": "欧歌多仓", "url": "http://tv.nxog.top/api.php?id=1"},
    {"type": 0, "name": "小盒子4K", "url": "http://xhztv.top/4k.json"},
    {"type": 0, "name": "香雅情", "url": "https://raw.kkgithub.com/xyq254245/xyqonlinerule/main/XYQTVBox.json"},
    {"type": 1, "name": "范明明 IPv4", "url": "https://live.fanmingming.com/tv/m3u/ipv4/result.m3u"},
    {"type": 1, "name": "范明明 IPv6", "url": "https://live.fanmingming.com/tv/m3u/ipv6/result.m3u"},
    {"type": 0, "name": "MXTVBox", "url": "assets://default_config.json"},
]

TYPE_NOTE = {0: "点播配置", 1: "直播 M3U"}


async def main() -> None:
    existing = await tvbox_service.list_sources()
    by_url = {item.url: item for item in existing}

    added = 0
    skipped = 0
    for index, item in enumerate(SOURCES):
        url = item["url"].strip()
        name = item["name"].strip()
        note = TYPE_NOTE.get(item["type"], f"type={item['type']}")
        if item["url"].startswith("assets://"):
            note = f"{note} · 本地 assets，服务端无法远程测试"

        if url in by_url:
            skipped += 1
            print(f"skip (exists): {name}")
            continue

        created = await tvbox_service.create_source(
            TvboxSourceCreate(name=name, url=url, enabled=True, note=note)
        )
        await tvbox_service.update_source(
            created.id,
            TvboxSourceUpdate(sort_order=index),
        )
        by_url[url] = created
        added += 1
        print(f"added: {name}")

    total = await tvbox_service.list_sources()
    print(f"\nDone: added={added}, skipped={skipped}, total={len(total)}")


if __name__ == "__main__":
    asyncio.run(main())
