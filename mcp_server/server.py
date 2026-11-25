"""MCP Server for Family Media Center - exposes download tools via Model Context Protocol."""

import os
import json
from typing import Any, Optional
from urllib.parse import quote

import httpx
from mcp.server.fastmcp import FastMCP

from playlist_ops import matching_rows, mutation_targets, resolve_playlist
from uploads import post_local_file

BASE_URL = os.environ.get("FAMILY_MEDIACENTER_URL", "http://127.0.0.1:18026")
API_KEY = os.environ.get("FAMILY_MEDIACENTER_API_KEY", "")

mcp = FastMCP(
    "family-media",
    instructions="家庭媒体中心：下载音视频，按文件名管理播放列表，上传本机电子书和音视频，并查询分享页的观看和阅读统计。",
)


def _headers() -> dict[str, str]:
    h: dict[str, str] = {"Content-Type": "application/json"}
    if API_KEY:
        h["X-API-Key"] = API_KEY
    return h


def _auth_headers() -> dict[str, str]:
    if not API_KEY:
        return {}
    return {"X-API-Key": API_KEY}


def _upload_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(3600.0, connect=30.0))


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
                "share_hidden": bool(item.get("share_hidden")),
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
async def rename_playlist(playlist_id: int, name: str) -> str:
    """重命名播放列表。只改显示名称，分享链接和分享开关保持不变。"""
    try:
        result = await _request("PUT", f"/api/v1/playlists/{playlist_id}", {"name": name})
        return _dump(result)
    except RuntimeError as exc:
        return _fail(str(exc))


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
async def set_playlist_item_share_hide(playlist_id: int, item_id: int, hidden: bool) -> str:
    """临时隐藏或恢复播放列表里的一个文件。hidden 为 true 时，分享页今天不展示也不能播放，第二天自动恢复。hidden 为 false 时立即恢复。不删除磁盘文件，不影响其他条目。"""
    try:
        result = await _request(
            "PUT",
            f"/api/v1/playlists/{playlist_id}/items/{item_id}/share-hide",
            {"hidden": hidden},
        )
        return _dump(result)
    except RuntimeError as exc:
        return _fail(str(exc))


@mcp.tool()
async def remove_playlist_item(playlist_id: int, item_id: int) -> str:
    """Remove an item from a playlist."""
    result = await _request(
        "DELETE", f"/api/v1/playlists/{playlist_id}/items/{item_id}"
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def share_watch_stats(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> str:
    """查询分享页观看统计。返回每台设备的观看时长、作息和热点。from_date/to_date 为 YYYY-MM-DD，省略则最近 7 天。只保留最近一个月的记录。用设备名和 IP 区分观看者，不要自行把设备说成某个孩子。"""
    params = []
    if from_date:
        params.append(f"from={from_date}")
    if to_date:
        params.append(f"to={to_date}")
    path = "/api/v1/share/stats"
    if params:
        path += "?" + "&".join(params)
    try:
        result = await _request("GET", path)
        return _dump(result)
    except RuntimeError as exc:
        return _fail(str(exc))


@mcp.tool()
async def share_read_stats(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> str:
    """查询分享阅读统计。返回每台设备的阅读时长、作息和打开过的书。from_date/to_date 为 YYYY-MM-DD，省略则最近 7 天。只保留最近一个月的记录。用设备名和 IP 区分阅读者，不要自行把设备说成某个孩子。"""
    params = []
    if from_date:
        params.append(f"from={from_date}")
    if to_date:
        params.append(f"to={to_date}")
    path = "/api/v1/share/read-stats"
    if params:
        path += "?" + "&".join(params)
    try:
        result = await _request("GET", path)
        return _dump(result)
    except RuntimeError as exc:
        return _fail(str(exc))


@mcp.tool()
async def get_share_eye_care() -> str:
    """查看分享页护眼设置。默认开启，连续看视频或读电子书 30 分钟后休息 15 分钟。同一台设备的视频和图书合在一起计时。"""
    try:
        result = await _request("GET", "/api/v1/share/eye-care")
        return _dump(result)
    except RuntimeError as exc:
        return _fail(str(exc))


@mcp.tool()
async def set_share_eye_care(enabled: bool, play_minutes: int = 30, rest_minutes: int = 15) -> str:
    """设置分享页护眼。enabled 为开关。play_minutes 是连续使用多久后休息，1–240。rest_minutes 是必须休息多久，1–180。按设备分别计时，视频和图书共用。"""
    try:
        result = await _request(
            "PUT",
            "/api/v1/share/eye-care",
            {
                "enabled": enabled,
                "play_minutes": play_minutes,
                "rest_minutes": rest_minutes,
            },
        )
        return _dump(result)
    except RuntimeError as exc:
        return _fail(str(exc))


@mcp.tool()
async def share_eye_care_status() -> str:
    """查看每台设备的时长管控。返回是否在休息、剩余休息秒数、本轮已使用秒数。视频和电子书合在一起计时。用设备名和 IP 区分，不要自行把设备说成某个孩子。"""
    try:
        result = await _request("GET", "/api/v1/share/eye-care/status")
        return _dump(result)
    except RuntimeError as exc:
        return _fail(str(exc))


@mcp.tool()
async def reset_share_eye_care(device_id: int) -> str:
    """解除某台设备当前的休息，并让这一轮使用时长从头计算。device_id 来自 share_eye_care_status。不改变护眼开关和时长，也不影响其他设备。"""
    try:
        result = await _request("POST", f"/api/v1/share/eye-care/devices/{device_id}/reset")
        return _dump(result)
    except RuntimeError as exc:
        return _fail(str(exc))


@mcp.tool()
async def set_share_device_access(device_id: int, allowed: bool) -> str:
    """允许或拒绝某台设备观看分享视频和分享图书。新设备默认允许。device_id 来自 share_watch_stats。"""
    try:
        result = await _request(
            "PUT",
            f"/api/v1/share/devices/{device_id}",
            {"allowed": allowed},
        )
        return _dump(result)
    except RuntimeError as exc:
        return _fail(str(exc))


def _material_query(path: str) -> str:
    return quote(path or "", safe="")


@mcp.tool()
async def list_ebooks(path: str = "") -> str:
    """列出电子书库。path 是相对书库根目录的子目录，空字符串表示根目录。只含 .pdf .epub .txt .md 和子目录。"""
    combined: dict | None = None
    page = 1
    try:
        while page <= 20:
            query = (
                f"/api/v1/materials?page_size=100&page={page}&path={_material_query(path)}"
            )
            result = await _request("GET", query)
            if not isinstance(result, dict):
                return _dump(result)
            entries = list(result.get("entries") or [])
            if combined is None:
                combined = result
                combined["entries"] = entries
            else:
                combined["entries"].extend(entries)
            total_pages = int(result.get("total_pages") or 1)
            if page >= total_pages:
                break
            page += 1
        if combined is not None:
            combined["page"] = 1
            combined["page_size"] = len(combined["entries"])
        return _dump(combined or {})
    except RuntimeError as exc:
        return _fail(str(exc))


@mcp.tool()
async def import_ebook(url: str, sub_path: str = "", filename: str = "") -> str:
    """把 http/https 直链下载进电子书库。只接受 .pdf .epub .txt .md。sub_path 是已有目录，filename 可指定保存名。返回下载任务，再用 get_task 看进度。"""
    body: dict[str, str] = {"url": url}
    if sub_path:
        body["sub_path"] = sub_path
    if filename:
        body["filename"] = filename
    try:
        result = await _request("POST", "/api/v1/materials/import", body)
        return _dump(result)
    except RuntimeError as exc:
        return _fail(str(exc))


@mcp.tool()
async def upload_ebook(file_path: str, sub_path: str = "") -> str:
    """把本机电子书文件上传到书库。file_path 是这台电脑上的路径。sub_path 是已有目录，空字符串表示书库根目录。支持 .pdf .epub .txt .md。同名文件会拒绝。"""
    try:
        async with _upload_client() as client:
            result = await post_local_file(
                client,
                f"{BASE_URL.rstrip('/')}/api/v1/materials/upload",
                file_path,
                data={"sub_path": sub_path},
                headers=_auth_headers(),
            )
        return _dump(result)
    except (OSError, ValueError, RuntimeError) as exc:
        return _fail(str(exc))


@mcp.tool()
async def upload_media(
    file_path: str,
    playlist_name: str = "",
    playlist_id: Optional[int] = None,
) -> str:
    """把本机音视频文件上传并加入播放列表。file_path 是这台电脑上的路径。playlist_name 按名称匹配，playlist_id 优先。都不传则加入默认列表「全部下载」。"""
    try:
        playlists = await _playlists()
        if playlist_id is not None:
            chosen = next(
                (row for row in playlists if row.get("id") == playlist_id), None
            )
            if chosen is None:
                return _fail("找不到这个播放列表")
        elif playlist_name.strip():
            chosen_or_error = _playlist_or_error(playlists, playlist_name)
            if isinstance(chosen_or_error, str):
                return chosen_or_error
            chosen = chosen_or_error
        else:
            chosen = next((row for row in playlists if row.get("is_default")), None)
            if chosen is None:
                return _fail("没有默认播放列表")
        async with _upload_client() as client:
            result = await post_local_file(
                client,
                f"{BASE_URL.rstrip('/')}/api/v1/playlists/{chosen['id']}/upload",
                file_path,
                headers=_auth_headers(),
            )
        return _dump(result)
    except (OSError, ValueError, RuntimeError) as exc:
        return _fail(str(exc))


@mcp.tool()
async def create_ebook_folder(path: str) -> str:
    """在电子书库新建目录。path 相对书库根目录，可以一次建立多级目录。"""
    try:
        result = await _request("POST", "/api/v1/materials/folders", {"path": path})
        return _dump(result)
    except RuntimeError as exc:
        return _fail(str(exc))


@mcp.tool()
async def rename_ebook(path: str, name: str) -> str:
    """重命名电子书或目录。name 只是新的最后一段名字。文件必须仍是 .pdf .epub .txt .md。分享链接不变，分享记录里的路径会跟着更新。"""
    try:
        result = await _request(
            "POST", "/api/v1/materials/rename", {"path": path, "name": name}
        )
        return _dump(result)
    except RuntimeError as exc:
        return _fail(str(exc))


@mcp.tool()
async def move_ebook(path: str, dest: str = "") -> str:
    """把电子书或目录移动到书库里的另一个目录。dest 为空表示书库根目录，且必须已经存在。已有分享会跟着改路径。"""
    try:
        result = await _request(
            "POST", "/api/v1/materials/move", {"path": path, "dest": dest}
        )
        return _dump(result)
    except RuntimeError as exc:
        return _fail(str(exc))


@mcp.tool()
async def delete_ebook(path: str) -> str:
    """删除电子书或目录。删除目录会连同里面的书一起删除，并停用命中的分享链接。不能删除书库根目录。"""
    query = f"/api/v1/materials?path={_material_query(path)}"
    try:
        result = await _request("DELETE", query)
        return _dump(result)
    except RuntimeError as exc:
        return _fail(str(exc))


if __name__ == "__main__":
    mcp.run()
