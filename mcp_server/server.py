"""MCP Server for Family Media Center - exposes download tools via Model Context Protocol."""

import os
import json
from typing import Optional

import httpx
from mcp.server.fastmcp import FastMCP

BASE_URL = os.environ.get("FAMILY_MEDIACENTER_URL", "http://127.0.0.1:18026")
API_KEY = os.environ.get("FAMILY_MEDIACENTER_API_KEY", "")

mcp = FastMCP("family-mediacenter")


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
        r.raise_for_status()
        if not r.content:
            return {}
        return r.json()


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
async def list_playlist_items(playlist_id: Optional[int] = None) -> str:
    """List items in a playlist for playback or carousel. playlist_id omitted = default playlist."""
    if playlist_id is None:
        path = "/api/v1/playlists/default/items"
    else:
        path = f"/api/v1/playlists/{playlist_id}/items"
    result = await _request("GET", path)
    return json.dumps(result, ensure_ascii=False, indent=2)


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
