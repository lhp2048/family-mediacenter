"""Build test unit tree for single / multi warehouse configs."""

from __future__ import annotations

from typing import Any

from app.tvbox_testing.config_parse import extract_sub_urls, summarize_tvbox_config
from app.tvbox_testing.types import UnitType


def build_unit_tree(
    source_name: str,
    source_url: str,
    config: dict[str, Any] | None,
    *,
    config_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = config_summary or (summarize_tvbox_config(config) if config else {})
    root: dict[str, Any] = {
        "id": "root",
        "type": UnitType.SOURCE.value,
        "name": source_name,
        "url": source_url,
        "config_type": summary.get("type", "unknown"),
        "children": [],
    }
    if not config:
        return root

    kind = summary.get("type")
    if kind == "multi_warehouse":
        for index, sub_url in enumerate(extract_sub_urls(config)):
            root["children"].append(
                {
                    "id": f"sub_{index}",
                    "type": UnitType.SUB_CONFIG.value,
                    "name": f"子仓 {index + 1}",
                    "url": sub_url,
                    "children": [],
                }
            )
    else:
        sites = config.get("sites") or config.get("apis") or []
        if isinstance(sites, list):
            for index, site in enumerate(sites[:20]):
                if not isinstance(site, dict):
                    continue
                root["children"].append(
                    {
                        "id": f"site_{index}",
                        "type": UnitType.SITE.value,
                        "name": str(site.get("name") or site.get("key") or f"站点{index + 1}"),
                        "url": str(site.get("api") or ""),
                        "meta": {
                            "key": site.get("key"),
                            "type": site.get("type"),
                            "searchable": site.get("searchable"),
                        },
                        "children": [],
                    }
                )

        lives = config.get("lives") or []
        if isinstance(lives, list):
            for gindex, group in enumerate(lives[:10]):
                if not isinstance(group, dict):
                    continue
                group_node: dict[str, Any] = {
                    "id": f"live_group_{gindex}",
                    "type": UnitType.LIVE_GROUP.value,
                    "name": str(group.get("group") or group.get("name") or f"直播组{gindex + 1}"),
                    "url": str(group.get("url") or ""),
                    "children": [],
                }
                channels = group.get("channels") or []
                if isinstance(channels, list):
                    for cindex, ch in enumerate(channels[:30]):
                        if isinstance(ch, dict):
                            group_node["children"].append(
                                {
                                    "id": f"live_{gindex}_{cindex}",
                                    "type": UnitType.LIVE_CHANNEL.value,
                                    "name": str(ch.get("name") or f"频道{cindex + 1}"),
                                    "url": str(ch.get("url") or ""),
                                    "children": [],
                                }
                            )
                        elif isinstance(ch, str) and ch.strip():
                            group_node["children"].append(
                                {
                                    "id": f"live_{gindex}_{cindex}",
                                    "type": UnitType.LIVE_CHANNEL.value,
                                    "name": f"频道{cindex + 1}",
                                    "url": ch.strip(),
                                    "children": [],
                                }
                            )
                root["children"].append(group_node)

    return root
