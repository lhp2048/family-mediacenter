"""Name-based playlist matching for the MCP server. No network or MCP imports."""
from __future__ import annotations

import fnmatch
import re
from typing import Any, Iterable


def split_patterns(raw: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,，]", raw or "") if part.strip()]


def name_matches(query: str, *fields: str) -> bool:
    needle = (query or "").strip().casefold()
    if not needle:
        return False
    values = [str(value or "").casefold() for value in fields if str(value or "").strip()]
    if any(ch in needle for ch in "*?"):
        return any(fnmatch.fnmatch(value, needle) for value in values)
    return any(needle in value for value in values)


def _row_fields(row: dict[str, Any], fields: Iterable[str]) -> list[str]:
    return [str(row.get(field) or "") for field in fields]


def matching_rows(query: str, rows: list[dict[str, Any]], fields: tuple[str, ...]) -> list[dict[str, Any]]:
    patterns = split_patterns(query)
    if not patterns:
        return []
    chosen: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        values = _row_fields(row, fields)
        if not any(name_matches(pattern, *values) for pattern in patterns):
            continue
        key = str(row.get("rel_path") or row.get("id") or id(row))
        if key in seen:
            continue
        seen.add(key)
        chosen.append(row)
    return chosen


def _is_exact(query: str, row: dict[str, Any]) -> bool:
    needle = query.strip().casefold()
    rel = str(row.get("rel_path") or "")
    base = rel.replace("\\", "/").rsplit("/", 1)[-1]
    values = [
        str(row.get("name") or ""),
        str(row.get("title") or ""),
        rel,
        base,
    ]
    return any(value.casefold() == needle for value in values if value.strip())


def mutation_targets(
    query: str, rows: list[dict[str, Any]], fields: tuple[str, ...]
) -> tuple[list[dict[str, Any]], str]:
    """Pick rows to remove or move.

    A wildcard selects every match. A plain name selects an exact hit, or the
    only substring hit. Several substring hits are refused so a short keyword
    cannot clear a whole list.
    """
    patterns = split_patterns(query)
    if not patterns:
        return [], "请提供文件名"
    matches = matching_rows(query, rows, fields)
    if not matches:
        return [], ""
    wildcard = any(any(ch in pattern for ch in "*?") for pattern in patterns)
    if wildcard or len(patterns) > 1:
        return matches, ""
    exact = [row for row in matches if _is_exact(patterns[0], row)]
    if exact:
        return exact, ""
    if len(matches) == 1:
        return matches, ""
    preview = "、".join(
        str(row.get("rel_path") or row.get("name") or row.get("title") or "")
        for row in matches[:12]
    )
    extra = "" if len(matches) <= 12 else f" 等 {len(matches)} 个"
    return [], f"「{patterns[0]}」匹配到多个文件：{preview}{extra}。请写完整文件名，或用通配符如 {patterns[0]}*"


def resolve_playlist(playlists: list[dict[str, Any]], name: str) -> dict[str, Any]:
    query = (name or "").strip()
    if not query:
        raise ValueError("请提供播放列表名称")
    exact = [row for row in playlists if str(row.get("name") or "") == query]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise ValueError(f"有多个同名播放列表「{query}」，请改用 ID")
    folded = query.casefold()
    partial = [
        row for row in playlists if folded in str(row.get("name") or "").casefold()
    ]
    if len(partial) == 1:
        return partial[0]
    known = "、".join(str(row.get("name") or "") for row in playlists) or "（空）"
    if not partial:
        raise ValueError(f"找不到播放列表「{query}」。现有：{known}")
    hit = "、".join(str(row.get("name") or "") for row in partial)
    raise ValueError(f"「{query}」匹配到多个列表：{hit}")
