"""Send a local file to Family Media Center upload endpoints."""

from pathlib import Path
from typing import Any, Optional

import httpx


def resolve_local_file(file_path: str) -> Path:
    raw = (file_path or "").strip()
    if not raw:
        raise ValueError("请提供本机文件路径")
    path = Path(raw).expanduser().resolve()
    if not path.is_file():
        raise ValueError("文件不存在")
    return path


async def post_local_file(
    client: httpx.AsyncClient,
    url: str,
    file_path: str,
    *,
    data: Optional[dict[str, str]] = None,
    headers: Optional[dict[str, str]] = None,
) -> Any:
    path = resolve_local_file(file_path)
    with path.open("rb") as handle:
        response = await client.post(
            url,
            headers=headers,
            data=data or {},
            files={"file": (path.name, handle)},
        )
    if response.status_code >= 400:
        detail: Any = response.text
        try:
            body = response.json()
            detail = body.get("detail", detail)
        except Exception:
            pass
        raise RuntimeError(str(detail))
    if not response.content:
        return {}
    return response.json()
