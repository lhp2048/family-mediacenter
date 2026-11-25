#!/usr/bin/env python3
"""Temporarily hide a playlist file from the share page until the next day."""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    import asyncio
    from datetime import timedelta

    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from app.config import load_settings
    from app.db import async_session, init_db
    from app.main import app
    from app.models.playlist import PlaylistCreate, PlaylistItemORM
    from app.services.playlist_service import playlist_service
    from app.services.share_watch import local_naive

    asyncio.run(init_db())
    settings = load_settings()
    headers = {"X-API-Key": settings.server.api_key} if settings.server.api_key else {}
    mark = uuid.uuid4().hex[:8]
    names = (f"hide-{mark}-a.mp4", f"hide-{mark}-b.mp4")
    media = ROOT / "downloads" / "multimedia"
    media.mkdir(parents=True, exist_ok=True)
    for name in names:
        (media / name).write_bytes(b"fake-media")

    playlist_id = 0
    try:
        playlist = asyncio.run(
            playlist_service.create_playlist(PlaylistCreate(name=f"临时隐藏{mark}"))
        )
        playlist_id = playlist.id

        async def add_items() -> list[int]:
            async with async_session() as session:
                ids = []
                for index, name in enumerate(names):
                    row = PlaylistItemORM(
                        playlist_id=playlist_id,
                        rel_path=name,
                        title=name,
                        sort_order=index,
                    )
                    session.add(row)
                    await session.flush()
                    ids.append(row.id)
                await session.commit()
                return ids

        item_a, item_b = asyncio.run(add_items())
        client = TestClient(app)
        shared = client.post(f"/api/v1/playlists/{playlist_id}/share", headers=headers)
        assert shared.status_code == 200, shared.text
        token = shared.json()["share_token"]
        opened = client.get(f"/watch/{token}")
        assert opened.status_code == 200, opened.text

        listed = client.get(f"/api/v1/playlists/{playlist_id}/items", headers=headers)
        assert listed.status_code == 200, listed.text
        before = {row["id"]: row for row in listed.json()}
        assert before[item_a]["share_hidden"] is False

        missing = client.put(
            f"/api/v1/playlists/{playlist_id}/items/0/share-hide",
            headers=headers,
            json={"hidden": True},
        )
        assert missing.status_code == 404, missing.text

        hidden = client.put(
            f"/api/v1/playlists/{playlist_id}/items/{item_a}/share-hide",
            headers=headers,
            json={"hidden": True},
        )
        assert hidden.status_code == 200, hidden.text
        assert hidden.json()["share_hidden"] is True
        assert hidden.json()["share_hidden_on"] == local_naive().date().isoformat()

        watch = client.get(f"/api/v1/watch/{token}")
        assert watch.status_code == 200, watch.text
        shown = [row["id"] for row in watch.json()["items"]]
        assert item_a not in shown
        assert item_b in shown
        channel = client.get(f"/api/v1/playlists/{playlist_id}/live.m3u")
        assert channel.status_code == 200, channel.text
        assert names[0] not in channel.text
        assert names[1] in channel.text
        blocked = client.get(f"/api/v1/watch/{token}/media/{item_a}")
        assert blocked.status_code == 403, blocked.text
        assert blocked.json()["detail"] == "这个文件今天已隐藏"
        allowed = client.get(f"/api/v1/watch/{token}/media/{item_b}")
        assert allowed.status_code == 200, allowed.text

        progressed = client.put(
            f"/api/v1/watch/{token}/progress",
            json={"item_id": item_b, "position_sec": 3},
        )
        assert progressed.status_code == 200, progressed.text
        client.put(
            f"/api/v1/playlists/{playlist_id}/items/{item_b}/share-hide",
            headers=headers,
            json={"hidden": True},
        )
        resting = client.get(f"/api/v1/watch/{token}").json()
        assert item_b not in [row["id"] for row in resting["items"]]
        assert resting["progress"] is None

        async def age_hide() -> None:
            yesterday = (local_naive() - timedelta(days=1)).date().isoformat()
            async with async_session() as session:
                row = (
                    await session.execute(
                        select(PlaylistItemORM).where(PlaylistItemORM.id == item_a)
                    )
                ).scalar_one()
                row.share_hidden_on = yesterday
                await session.commit()

        asyncio.run(age_hide())
        resumed = client.get(f"/api/v1/watch/{token}")
        resumed_ids = [row["id"] for row in resumed.json()["items"]]
        assert item_a in resumed_ids
        assert item_b not in resumed_ids
        cleared = client.put(
            f"/api/v1/playlists/{playlist_id}/items/{item_b}/share-hide",
            headers=headers,
            json={"hidden": False},
        )
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["share_hidden"] is False
        assert cleared.json()["share_hidden_on"] == ""
        both = [row["id"] for row in client.get(f"/api/v1/watch/{token}").json()["items"]]
        assert item_a in both and item_b in both
        restored = client.get(f"/api/v1/playlists/{playlist_id}/live.m3u")
        assert names[0] in restored.text and names[1] in restored.text
    finally:
        if playlist_id:
            try:
                asyncio.run(playlist_service.delete_playlist(playlist_id))
            except Exception:
                pass
        for name in names:
            (media / name).unlink(missing_ok=True)
    print("OK: playlist share hide")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
