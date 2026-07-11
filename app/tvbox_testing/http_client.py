"""HTTP fetch with L1 reachability metadata."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from app.tvbox_testing.config_parse import local_url_blocked

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 12; TV) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}


@dataclass
class FetchResult:
    ok: bool
    message: str
    url: str
    http_status: Optional[int] = None
    latency_ms: int = 0
    redirects: list[dict[str, Any]] = field(default_factory=list)
    redirect_count: int = 0
    ban_type: Optional[str] = None
    body: str = ""
    content_type: str = ""
    raw_bytes: bytes = b""

    def to_summary(self) -> dict[str, Any]:
        return {
            "http_status": self.http_status,
            "latency_ms": self.latency_ms,
            "redirect_count": self.redirect_count,
            "redirects": self.redirects[:5],
            "ban_type": self.ban_type,
            "content_type": self.content_type,
        }


def _classify_http(status: int) -> tuple[bool, str, Optional[str]]:
    if status in (200, 201, 204):
        return True, "可达", None
    if status in (301, 302, 303, 307, 308):
        return True, f"重定向 HTTP {status}", None
    if status == 403:
        return False, "HTTP 403 禁止访问", "403"
    if status == 429:
        return False, "HTTP 429 请求过多", "429"
    if status >= 500:
        return False, f"HTTP {status} 服务端错误", "5xx"
    if status >= 400:
        return False, f"HTTP {status}", "4xx"
    return True, f"HTTP {status}", None


async def fetch_url(
    url: str,
    *,
    client: Optional[httpx.AsyncClient] = None,
    timeout: float = 15.0,
    max_body: int = 5 * 1024 * 1024,
) -> FetchResult:
    blocked = local_url_blocked(url)
    if blocked:
        return FetchResult(ok=False, message=blocked, url=url, latency_ms=0)

    started = time.perf_counter()

    async def _do(http: httpx.AsyncClient) -> FetchResult:
        try:
            response = await http.get(url)
        except httpx.TimeoutException:
            ms = int((time.perf_counter() - started) * 1000)
            return FetchResult(ok=False, message="请求超时", url=url, latency_ms=ms)
        except httpx.RequestError as exc:
            ms = int((time.perf_counter() - started) * 1000)
            return FetchResult(ok=False, message=f"网络错误: {exc}", url=url, latency_ms=ms)

        ms = int((time.perf_counter() - started) * 1000)
        redirects = [
            {"status": r.status_code, "url": str(r.url)}
            for r in response.history
        ]
        ok, message, ban = _classify_http(response.status_code)

        content_length = response.headers.get("content-length")
        if content_length and int(content_length) > max_body:
            return FetchResult(
                ok=False,
                message="响应体过大",
                url=url,
                http_status=response.status_code,
                latency_ms=ms,
                redirects=redirects,
                redirect_count=len(redirects),
                ban_type=ban,
            )

        raw = response.content
        if len(raw) > max_body:
            return FetchResult(
                ok=False,
                message=f"响应体超过 {max_body // (1024 * 1024)}MB",
                url=url,
                http_status=response.status_code,
                latency_ms=ms,
                redirects=redirects,
                redirect_count=len(redirects),
                ban_type=ban,
            )

        return FetchResult(
            ok=ok,
            message=message,
            url=url,
            http_status=response.status_code,
            latency_ms=ms,
            redirects=redirects,
            redirect_count=len(redirects),
            ban_type=ban,
            body=raw.decode("utf-8", errors="replace"),
            content_type=response.headers.get("content-type", ""),
            raw_bytes=raw,
        )

    if client is not None:
        return await _do(client)
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers=DEFAULT_HEADERS,
    ) as owned:
        return await _do(owned)
