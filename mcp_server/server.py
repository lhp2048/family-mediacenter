"""MCP Server for Family Media Center - exposes download tools via Model Context Protocol."""

import os
import json
from typing import Any, Optional

import httpx
from mcp.server.fastmcp import FastMCP

from playlist_ops import matching_rows, mutation_targets, resolve_playlist

BASE_URL = os.environ.get("FAMILY_MEDIACENTER_URL", "http://127.0.0.1:18026")
API_KEY = os.environ.get("FAMILY_MEDIACENTER_API_KEY", "")

mcp = FastMCP(
    "family-media",
    instructions="家庭媒体中心：下载音视频，并按文件名查看、创建和调整播放列表。",
)


def _headers() -> dict[str, str]:
    h: dict[str, str] = {"Content-Type": "application/json"}
    if API_KEY:
        h["X-API-Key"] = API_KEY
    return h


async def _request(method: str, path: str, body: Optional[dict] = None) -> dict:
    url = f"{BASE_URL.rstrip('/')}{path}"
    async with httpx.AsyncClient(timeout=60.0) as client:
        if method == "GET":
            r = await client.get(url, headers=_headers())
        elif method == "POST":
            r = await client.post(url, headers=_headers(), json=body or {})
        elif method == "PUT":
            r = await client.put(url, headers=_headers(), json=body or {})
        elif method == "DELETE":
            r = await client.delete(url, headers=_headers())
        else:
            raise ValueError(f"Unsupported method: {method}")
        if r.status_code >= 400:
            detail: Any = r.text
            try:
                body = r.json()
                detail = body.get("detail", detail)
            except Exception:
                pass
            raise RuntimeError(str(detail))
        if not r.content:
            return {}
        return r.json()


def _dump(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _fail(message: str) -> str:
    return _dump({"ok": False, "error": message})


def _as_list(result: Any) -> list[dict[str, Any]]:
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        items = result.get("items")
        if isinstance(items, list):
            return items
    return []


async def _playlists() -> list[dict[str, Any]]:
    return _as_list(await _request("GET", "/api/v1/playlists"))


async def _items(playlist_id: int) -> list[dict[str, Any]]:
    return _as_list(
        await _request("GET", f"/api/v1/playlists/{playlist_id}/items?probe=0")
    )


async def _media_files() -> list[dict[str, Any]]:
    return _as_list(await _request("GET", "/api/v1/media/files?probe=0"))


def _playlist_or_error(playlists: list[dict[str, Any]], name: str) -> dict[str, Any] | str:
    try:
        return resolve_playlist(playlists, name)
    except ValueError as exc:
        return _fail(str(exc))


async def _files_for_name(filename: str) -> list[dict[str, Any]]:
    files = await _media_files()
    return matching_rows(filename, files, ("name", "title", "rel_path"))


@mcp.tool()
async def create_download(
    url: str,
    engine: Optional[str] = None,
    output_dir: Optional[str] = None,
    options: Optional[str] = None,
) -> str:
    """Create a download task. url: target URL. engine: ytdlp|aria2|alist (optional). options: JSON string."""
    body: dict = {"url": url}
    if engine:
        body["engine"] = engine
    if output_dir:
        body["output_dir"] = output_dir
    if options:
        body["options"] = json.loads(options)
    result = await _request("POST", "/api/v1/downloads", body)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_task(task_id: int) -> str:
    """Get download task status by ID."""
    result = await _request("GET", f"/api/v1/tasks/{task_id}")
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def list_tasks(status: Optional[str] = None, page: Optional[int] = None) -> str:
    """List download tasks. status: pending|running|completed|failed|paused|cancelled (optional filter)."""
    path = "/api/v1/tasks"
    params = []
    if status:
        params.append(f"status={status}")
    if page is not None:
        params.append(f"page={page}")
        params.append("page_size=50")
    if params:
        path += "?" + "&".join(params)
    result = await _request("GET", path)
    if isinstance(result, dict) and "items" in result:
        return json.dumps(result, ensure_ascii=False, indent=2)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def cancel_task(task_id: int) -> str:
    """Cancel a download task by ID."""
    result = await _request("POST", f"/api/v1/tasks/{task_id}/cancel")
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_download_settings() -> str:
    """Get Family Media Center service settings."""
    result = await _request("GET", "/api/v1/settings")
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def health_check() -> str:
    """Check Family Media Center service and engine availability."""
    url = f"{BASE_URL.rstrip('/')}/health"
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(url)
        r.raise_for_status()
        return json.dumps(r.json(), ensure_ascii=False, indent=2)


@mcp.tool()
async def list_playlists() -> str:
    """List all multimedia playlists (including default auto-collection playlist)."""
    result = await _request("GET", "/api/v1/playlists")
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def list_playlist_items(
    playlist_id: Optional[int] = None,
    playlist_name: Optional[str] = None,
) -> str:
    """查看某个播放列表里的文件。传 playlist_name（列表名，可部分匹配）或 playlist_id。都不传则查看默认列表「全部下载」。"""
    try:
        if playlist_name and playlist_name.strip():
            playlists = await _playlists()
            found = _playlist_or_error(playlists, playlist_name)
            if isinstance(found, str):
                return found
            playlist_id = int(found["id"])
            items = await _items(playlist_id)
            return _dump({"playlist": found, "items": _brief_items(items)})
        if playlist_id is None:
            path = "/api/v1/playlists/default/items?probe=0"
            playlist = await _request("GET", "/api/v1/playlists/default")
        else:
            path = f"/api/v1/playlists/{playlist_id}/items?probe=0"
            playlist = await _request("GET", f"/api/v1/playlists/{playlist_id}")
        items = _as_list(await _request("GET", path))
        return _dump({"playlist": playlist, "items": _brief_items(items)})
    except RuntimeError as exc:
        return _fail(str(exc))


def _brief_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    brief = []
    for item in items:
        brief.append(
            {
                "id": item.get("id"),
                "name": item.get("name") or item.get("title"),
                "title": item.get("title"),
                "rel_path": item.get("rel_path"),
                "media_type": item.get("media_type"),
            }
        )
    return brief


@mcp.tool()
async def create_playlist_by_filename(playlist_name: str, filename: str) -> str:
    """按文件名创建播放列表，并把匹配到的音视频加进去。

    filename 写文件名的一部分，或通配符如 *.mp4。多个条件用逗号分隔。
    同名列表已存在时不会再新建，只把尚未收录的文件加进去。
    """
    try:
        patterns = [part.strip() for part in filename.replace("，", ",").split(",") if part.strip()]
        if not playlist_name.strip() or not patterns:
            return _fail("请同时提供播放列表名称和文件名")
        files = await _files_for_name(filename)
        if not files:
            return _fail(f"下载目录里没有匹配「{filename}」的音视频")
        playlists = await _playlists()
        existing = [row for row in playlists if str(row.get("name") or "") == playlist_name.strip()]
        created = False
        if existing:
            playlist = existing[0]
        else:
            playlist = await _request("POST", "/api/v1/playlists", {"name": playlist_name.strip()})
            created = True
        playlist_id = int(playlist["id"])
        added: list[str] = []
        skipped: list[str] = []
        for media in files:
            rel = str(media.get("rel_path") or "")
            if not rel:
                continue
            try:
                await _request(
                    "POST",
                    f"/api/v1/playlists/{playlist_id}/items",
                    {"rel_path": rel},
                )
                added.append(rel)
            except RuntimeError as exc:
                if "已在播放列表" in str(exc):
                    skipped.append(rel)
                else:
                    skipped.append(f"{rel}（{exc}）")
        return _dump(
            {
                "ok": True,
                "created": created,
                "playlist": playlist,
                "added": added,
                "already_in_playlist": skipped,
                "matched": [row.get("rel_path") for row in files],
            }
        )
    except RuntimeError as exc:
        return _fail(str(exc))


@mcp.tool()
async def remove_file_from_playlist(playlist_name: str, filename: str) -> str:
    """按文件名，把文件从指定播放列表中删除。不删除磁盘文件。

    列表名支持唯一的部分匹配。完整文件名，或只能对上一个文件时会删除。
    对上多个文件时不会删除，并返回候选路径。通配符（如 *.mp4）会删除该列表中的全部匹配。
    """
    try:
        playlists = await _playlists()
        playlist = _playlist_or_error(playlists, playlist_name)
        if isinstance(playlist, str):
            return playlist
        items, ambiguous = mutation_targets(
            filename,
            await _items(int(playlist["id"])),
            ("name", "title", "rel_path"),
        )
        if ambiguous:
            return _fail(ambiguous)
        if not items:
            return _fail(f"列表「{playlist.get('name')}」里没有匹配「{filename}」的文件")
        removed = []
        for item in items:
            await _request(
                "DELETE",
                f"/api/v1/playlists/{playlist['id']}/items/{item['id']}",
            )
            removed.append(
                {"id": item.get("id"), "name": item.get("name"), "rel_path": item.get("rel_path")}
            )
        return _dump(
            {
                "ok": True,
                "playlist": playlist.get("name"),
                "removed": removed,
            }
        )
    except RuntimeError as exc:
        return _fail(str(exc))


@mcp.tool()
async def move_file_to_playlist(
    filename: str,
    playlist_name: str,
    from_playlist: Optional[str] = None,
) -> str:
    """把匹配文件名的音视频放进目标播放列表。

    完整文件名，或只能对上一个文件时会移动。对上多个文件时不会改动，并返回候选路径。
    通配符会移动全部匹配。指定 from_playlist 时，只从那个列表移出；不指定时，会从其他列表移出。
    不删除磁盘文件。从「全部下载」移出后，若在页面上点「重新加载」，默认列表会再次收录本地文件。
    """
    try:
        if not filename.strip() or not playlist_name.strip():
            return _fail("请提供文件名和目标播放列表名称")
        playlists = await _playlists()
        target = _playlist_or_error(playlists, playlist_name)
        if isinstance(target, str):
            return target
        sources = playlists
        if from_playlist and from_playlist.strip():
            source = _playlist_or_error(playlists, from_playlist)
            if isinstance(source, str):
                return source
            sources = [source]
        files, ambiguous = mutation_targets(
            filename,
            await _media_files(),
            ("name", "title", "rel_path"),
        )
        if ambiguous:
            return _fail(ambiguous)
        rels = [str(row.get("rel_path") or "") for row in files if row.get("rel_path")]
        if not rels:
            return _fail(f"下载目录里没有匹配「{filename}」的音视频")
        added: list[str] = []
        already: list[str] = []
        for rel in rels:
            try:
                await _request(
                    "POST",
                    f"/api/v1/playlists/{target['id']}/items",
                    {"rel_path": rel},
                )
                added.append(rel)
            except RuntimeError as exc:
                if "已在播放列表" in str(exc):
                    already.append(rel)
                else:
                    return _fail(str(exc))
        removed: list[dict[str, Any]] = []
        rel_set = set(rels)
        for playlist in sources:
            if int(playlist["id"]) == int(target["id"]):
                continue
            for item in await _items(int(playlist["id"])):
                if str(item.get("rel_path") or "") not in rel_set:
                    continue
                await _request(
                    "DELETE",
                    f"/api/v1/playlists/{playlist['id']}/items/{item['id']}",
                )
                removed.append(
                    {
                        "playlist": playlist.get("name"),
                        "id": item.get("id"),
                        "rel_path": item.get("rel_path"),
                    }
                )
        return _dump(
            {
                "ok": True,
                "playlist": target.get("name"),
                "added": added,
                "already_in_playlist": already,
                "removed_from": removed,
            }
        )
    except RuntimeError as exc:
        return _fail(str(exc))


@mcp.tool()
async def delete_playlist_by_name(name: str) -> str:
    """按名称删除自定义播放列表。默认列表「全部下载」不能删除。名称支持唯一的部分匹配。"""
    try:
        playlists = await _playlists()
        playlist = _playlist_or_error(playlists, name)
        if isinstance(playlist, str):
            return playlist
        if playlist.get("is_default"):
            return _fail("不能删除默认播放列表")
        result = await _request("DELETE", f"/api/v1/playlists/{playlist['id']}")
        return _dump({"ok": True, "deleted": playlist.get("name"), "result": result})
    except RuntimeError as exc:
        return _fail(str(exc))


@mcp.tool()
async def list_media_files() -> str:
    """List video/audio files in the download directory (candidates for playlists)."""
    result = await _request("GET", "/api/v1/media/files")
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def create_playlist(name: str) -> str:
    """Create a new multimedia playlist."""
    result = await _request("POST", "/api/v1/playlists", {"name": name})
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def delete_playlist(playlist_id: int) -> str:
    """Delete a custom playlist (cannot delete the default playlist)."""
    result = await _request("DELETE", f"/api/v1/playlists/{playlist_id}")
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def add_playlist_item(
    playlist_id: int,
    rel_path: Optional[str] = None,
    task_id: Optional[int] = None,
) -> str:
    """Add a video/audio file to a playlist. Provide rel_path (under downloads/multimedia/) or completed task_id."""
    body: dict = {}
    if rel_path:
        body["rel_path"] = rel_path
    if task_id is not None:
        body["task_id"] = task_id
    result = await _request("POST", f"/api/v1/playlists/{playlist_id}/items", body)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def remove_playlist_item(playlist_id: int, item_id: int) -> str:
    """Remove an item from a playlist."""
    result = await _request(
        "DELETE", f"/api/v1/playlists/{playlist_id}/items/{item_id}"
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
