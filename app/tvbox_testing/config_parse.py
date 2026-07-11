"""Shared TVBox config parsing utilities."""

from __future__ import annotations

import base64
import binascii
import json
import re
from typing import Any, Optional

_BASE64_CHARS = re.compile(r"^[A-Za-z0-9+/=\s\-_]+$")
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")
_NUMBER_LITERAL = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?")


def _is_json_literal(token: str) -> bool:
    value = token.strip()
    if not value:
        return True
    lower = value.lower()
    if lower in ("true", "false", "null"):
        return True
    return bool(_NUMBER_LITERAL.fullmatch(value))


def _starts_json_keyword(text: str, index: int, word: str) -> bool:
    if not text.startswith(word, index):
        return False
    end = index + len(word)
    if end >= len(text):
        return True
    return text[end] in ",}] \t\r\n"


def _sanitize_tvbox_json_text(text: str) -> str:
    """Strip // and /* */ comments; join raw newlines inside JSON strings."""
    out: list[str] = []
    i = 0
    n = len(text)
    in_string = False
    escape = False

    while i < n:
        ch = text[i]
        if in_string:
            if escape:
                out.append(ch)
                escape = False
            elif ch == "\\":
                out.append(ch)
                escape = True
            elif ch == '"':
                out.append(ch)
                in_string = False
            elif ch in "\r\n":
                if ch == "\r" and i + 1 < n and text[i + 1] == "\n":
                    i += 1
                i += 1
                continue
            else:
                out.append(ch)
            i += 1
            continue

        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue

        if ch == "/" and i + 1 < n:
            nxt = text[i + 1]
            if nxt == "/":
                i += 2
                while i < n and text[i] not in "\r\n":
                    i += 1
                continue
            if nxt == "*":
                i += 2
                while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                    i += 1
                i = min(i + 2, n)
                continue

        out.append(ch)
        i += 1

    return "".join(out)


def _quote_bare_json_values(text: str) -> str:
    """Quote bare tokens after ':' outside JSON strings (e.g. \"key\":爱迪V2)."""
    out: list[str] = []
    i = 0
    n = len(text)
    in_string = False
    escape = False

    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            i += 1
            continue

        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue

        if ch == ":":
            out.append(ch)
            i += 1
            while i < n and text[i] in " \t\r\n":
                out.append(text[i])
                i += 1
            if i >= n:
                break

            nxt = text[i]
            if nxt in ('"', "[", "{"):
                continue
            if nxt == "-" and i + 1 < n and text[i + 1].isdigit():
                continue
            if nxt.isdigit():
                continue
            if (
                _starts_json_keyword(text, i, "true")
                or _starts_json_keyword(text, i, "false")
                or _starts_json_keyword(text, i, "null")
            ):
                continue

            start = i
            while i < n and text[i] not in ",}]":
                i += 1
            token = text[start:i]
            stripped = token.strip()
            if _is_json_literal(stripped):
                out.append(token)
            else:
                leading = token[: len(token) - len(token.lstrip())]
                trailing = token[len(token.rstrip()) :]
                escaped = stripped.replace("\\", "\\\\").replace('"', '\\"')
                out.append(leading)
                out.append(f'"{escaped}"')
                out.append(trailing)
            continue

        out.append(ch)
        i += 1

    return "".join(out)


def _relax_tvbox_json_text(text: str) -> str:
    """Best-effort cleanup before strict json.loads (TVBox / Gson-lenient subset)."""
    sanitized = _sanitize_tvbox_json_text(text)
    relaxed = _TRAILING_COMMA.sub(r"\1", sanitized)
    return _quote_bare_json_values(relaxed)


def _loads_json_text(text: str) -> tuple[Any, str]:
    """Parse JSON with strict first, then TVBox-oriented relaxed fallback."""
    try:
        return json.loads(text), "json"
    except json.JSONDecodeError:
        pass

    relaxed = _relax_tvbox_json_text(text)
    if relaxed != text:
        try:
            return json.loads(relaxed), "json_relaxed"
        except json.JSONDecodeError:
            pass

    try:
        import json5  # type: ignore[import-untyped]

        return json5.loads(text), "json5"
    except Exception:
        pass

    if relaxed != text:
        try:
            import json5  # type: ignore[import-untyped]

            return json5.loads(relaxed), "json5_relaxed"
        except Exception:
            pass

    raise json.JSONDecodeError("Expecting value", text, 0)


def _try_loads_json_text(text: str) -> tuple[Optional[Any], str]:
    try:
        return _loads_json_text(text)
    except json.JSONDecodeError:
        return None, "unparsed"


def extract_sub_urls(data: dict[str, Any]) -> list[str]:
    raw = data.get("urls") or data.get("storeHouse")
    if not isinstance(raw, list):
        return []
    urls: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            urls.append(item.strip())
        elif isinstance(item, dict):
            for key in ("url", "sourceUrl", "path", "json", "src"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    urls.append(value.strip())
                    break
    return urls


def summarize_tvbox_config(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {"valid_json": False}

    summary: dict[str, Any] = {"valid_json": True}
    for key in ("sites", "parses", "lives", "rules", "flags", "ads", "apis"):
        value = data.get(key)
        if isinstance(value, list):
            summary[f"{key}_count"] = len(value)
        elif value is not None:
            summary[key] = True

    urls = data.get("urls")
    store = data.get("storeHouse")
    if isinstance(urls, list):
        summary["urls_count"] = len(urls)
        summary["urls_resolvable"] = len(extract_sub_urls(data))
    elif isinstance(store, list):
        summary["urls_count"] = len(store)
        summary["urls_resolvable"] = len(extract_sub_urls({"urls": store}))

    spider = data.get("spider")
    if isinstance(spider, str) and spider.strip():
        summary["spider"] = spider.strip()[:120]

    if summary.get("urls_count", 0) > 0:
        summary["type"] = "multi_warehouse"
    elif summary.get("sites_count", 0) > 0 or summary.get("apis_count", 0) > 0:
        summary["type"] = "sites"
    elif summary.get("lives_count", 0) > 0:
        summary["type"] = "lives"
    else:
        summary["type"] = "unknown"

    return summary


def format_summary_text(summary: dict[str, Any]) -> str:
    if summary.get("format") == "live_m3u":
        return "直播 M3U 可用"
    if summary.get("format") == "live_txt":
        return "直播 TXT 可用"
    if not summary.get("valid_json", True):
        return "非 JSON 对象"
    parts: list[str] = []
    kind = summary.get("type")
    if kind == "multi_warehouse":
        count = summary.get("urls_resolvable", summary.get("urls_count", 0))
        parts.append(f"多仓 {count} 个子源")
    elif kind == "sites":
        n = summary.get("sites_count", 0) or summary.get("apis_count", 0)
        parts.append(f"站点 {n} 个")
    if summary.get("parses_count"):
        parts.append(f"解析 {summary['parses_count']}")
    if summary.get("lives_count"):
        parts.append(f"直播 {summary['lives_count']}")
    if summary.get("spider"):
        parts.append("含 Spider")
    if summary.get("parse_format"):
        parts.append(f"格式 {summary['parse_format']}")
    probe = summary.get("child_probe")
    if isinstance(probe, dict) and probe.get("probed", 0) > 0:
        ok_n = probe.get("ok", 0)
        if ok_n <= 0:
            total = probe.get("total", probe["probed"])
            parts.append(f"子源 0/{total} 可用")
        else:
            parts.append(f"子源 {ok_n}/{probe['probed']} 可用")
    child_sites = summary.get("child_sites_count")
    if child_sites:
        parts.append(f"子仓站点 {child_sites} 个")
    return " · ".join(parts) if parts else "JSON 结构未识别为常见 TVBox 配置"


def looks_like_base64(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if len(compact) < 16 or len(compact) % 4 == 1:
        return False
    return bool(_BASE64_CHARS.match(compact))


def decode_base64_payload(text: str) -> Optional[Any]:
    compact = re.sub(r"\s+", "", text)
    compact = compact.replace("-", "+").replace("_", "/")
    pad = (-len(compact)) % 4
    if pad:
        compact += "=" * pad
    try:
        raw = base64.b64decode(compact, validate=False)
    except (binascii.Error, ValueError):
        return None
    for encoding in ("utf-8", "gb18030", "latin-1"):
        try:
            decoded_text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        decoded_text = decoded_text.strip().lstrip("\ufeff")
        if not decoded_text:
            continue
        data, _fmt = _try_loads_json_text(decoded_text)
        if data is not None:
            return data
    return None


def parse_tvbox_body(body: str) -> tuple[Optional[Any], str]:
    text = body.strip().lstrip("\ufeff")
    if not text:
        return None, "empty"

    data, fmt = _try_loads_json_text(text)
    if data is not None:
        return data, fmt

    if "**" in text:
        _, _, tail = text.partition("**")
        tail = tail.strip()
        if tail:
            data = decode_base64_payload(tail)
            if data is not None:
                return data, "base64_prefixed"
            data, fmt = _try_loads_json_text(tail)
            if data is not None:
                return data, "json_suffix" if fmt == "json" else fmt

    if looks_like_base64(text):
        data = decode_base64_payload(text)
        if data is not None:
            return data, "base64"

    return None, "unparsed"


def validate_config_content(data: dict[str, Any], summary: dict[str, Any]) -> tuple[bool, str]:
    kind = summary.get("type")
    if kind == "multi_warehouse":
        resolvable = summary.get("urls_resolvable", summary.get("urls_count", 0))
        if resolvable == 0:
            return False, "多仓配置 urls 为空或无有效地址"
    elif kind == "sites":
        sites = summary.get("sites_count", 0) or summary.get("apis_count", 0)
        if sites == 0:
            return False, "站点列表 sites/apis 为空"
    elif kind == "lives":
        if summary.get("lives_count", 0) == 0:
            return False, "直播列表 lives 为空"
    elif kind == "unknown" and not summary.get("spider"):
        return False, "未发现 sites / urls / lives / spider 等 TVBox 字段"
    return True, "可用"


def local_url_blocked(url: str) -> Optional[str]:
    lowered = url.strip().lower()
    if lowered.startswith(("assets://", "file://", "content://")):
        return "本地协议地址，无法远程测试"
    return None


def resolve_availability(ok: bool, summary: dict[str, Any]) -> str:
    if not ok:
        return "failed"
    child = summary.get("child_probe")
    if isinstance(child, dict) and child.get("probed", 0) > 0:
        child_ok = child.get("ok", 0)
        probed = child["probed"]
        if child_ok <= 0:
            return "partial"
        if child_ok < probed:
            return "partial"
    return "full"


def is_live_url(url: str) -> bool:
    path = url.lower().split("?", 1)[0]
    return path.endswith((".m3u", ".m3u8", ".txt"))


def site_label(site: dict[str, Any]) -> str:
    return str(site.get("name") or site.get("key") or site.get("api") or "站点")[:64]
