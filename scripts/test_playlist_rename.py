#!/usr/bin/env python3
"""Renaming a playlist keeps its share link."""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    import asyncio

    from fastapi.testclient import TestClient

    from app.config import load_settings
    from app.db import init_db
    from app.main import app
    from app.models.playlist import PlaylistCreate
    from app.services.playlist_service import playlist_service

    asyncio.run(init_db())
    settings = load_settings()
    headers = {"X-API-Key": settings.server.api_key} if settings.server.api_key else {}
    mark = uuid.uuid4().hex[:8]
    playlist_id = 0
    try:
        playlist = asyncio.run(
            playlist_service.create_playlist(PlaylistCreate(name=f"改名前{mark}"))
        )
        playlist_id = playlist.id
        client = TestClient(app)
        shared = client.post(f"/api/v1/playlists/{playlist_id}/share", headers=headers)
        assert shared.status_code == 200, shared.text
        token = shared.json()["share_token"]
        share_url = shared.json()["share_url"]
        assert token and share_url.endswith(f"/watch/{token}")

        missing = client.put(
            "/api/v1/playlists/0",
            headers=headers,
            json={"name": "不存在"},
        )
        assert missing.status_code == 404, missing.text
        blank = client.put(
            f"/api/v1/playlists/{playlist_id}",
            headers=headers,
            json={"name": "  "},
        )
        assert blank.status_code == 400, blank.text

        renamed = client.put(
            f"/api/v1/playlists/{playlist_id}",
            headers=headers,
            json={"name": f" 改名后{mark} "},
        )
        assert renamed.status_code == 200, renamed.text
        body = renamed.json()
        assert body["name"] == f"改名后{mark}"
        assert body["share_enabled"] is True
        assert body["share_token"] == token
        assert body["share_url"] == share_url

        page = client.get(f"/watch/{token}")
        assert page.status_code == 200, page.text
        assert f"改名后{mark}" in page.text
    finally:
        if playlist_id:
            try:
                asyncio.run(playlist_service.delete_playlist(playlist_id))
            except Exception:
                pass
    print("OK: playlist rename keeps share")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
