#!/usr/bin/env python3
"""Smoke-test playlist share page, reorder, progress, autoplay."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    import asyncio

    from fastapi.testclient import TestClient

    from app.db import init_db
    from app.main import app
    from app.services.playlist_service import playlist_service

    asyncio.run(init_db())

    async def seed():
        pl = await playlist_service.create_playlist(
            __import__("app.models.playlist", fromlist=["PlaylistCreate"]).PlaylistCreate(
                name="share-smoke"
            )
        )
        # add two fake items via ORM
        from app.db import async_session
        from app.models.playlist import PlaylistItemORM

        async with async_session() as session:
            session.add(
                PlaylistItemORM(
                    playlist_id=pl.id,
                    rel_path="a.mp4",
                    title="长标题甲 " + ("测" * 40),
                    sort_order=0,
                )
            )
            session.add(
                PlaylistItemORM(
                    playlist_id=pl.id,
                    rel_path="b.mp4",
                    title="长标题乙",
                    sort_order=1,
                )
            )
            await session.commit()
        return pl.id

    playlist_id = asyncio.run(seed())
    client = TestClient(app)

    # enable share
    r = client.post(f"/api/v1/playlists/{playlist_id}/share")
    assert r.status_code == 200, r.text
    share = r.json()
    assert share["share_enabled"] is True
    token = share["share_token"]
    assert token
    assert f"/watch/{token}" in share["share_url"]

    page = client.get(f"/watch/{token}")
    assert page.status_code == 200
    assert "长标题" in page.text or "share-smoke" in page.text

    # watch JSON — files may not exist so items can be empty; still 200
    w = client.get(f"/api/v1/watch/{token}")
    assert w.status_code == 200, w.text
    body = w.json()
    assert body["name"] == "share-smoke"
    assert body["autoplay"] is False

    # create real files so items appear
    media = ROOT / "downloads" / "multimedia"
    media.mkdir(parents=True, exist_ok=True)
    (media / "a.mp4").write_bytes(b"fake")
    (media / "b.mp4").write_bytes(b"fake")

    # fix rel paths to storage-relative style used by resolve
    from app.db import async_session
    from app.models.playlist import PlaylistItemORM
    from sqlalchemy import select

    async def fix_paths():
        async with async_session() as session:
            result = await session.execute(
                select(PlaylistItemORM).where(PlaylistItemORM.playlist_id == playlist_id)
            )
            rows = result.scalars().all()
            for row in rows:
                if row.rel_path == "a.mp4":
                    row.rel_path = "a.mp4"
                if row.rel_path == "b.mp4":
                    row.rel_path = "b.mp4"
            await session.commit()
            return [(r.id, r.title) for r in rows]

    item_ids = asyncio.run(fix_paths())
    assert len(item_ids) == 2

    w2 = client.get(f"/api/v1/watch/{token}")
    assert w2.status_code == 200
    items = w2.json()["items"]
    assert len(items) == 2, items
    assert items[0]["sort_order"] <= items[1]["sort_order"]

    # reorder
    reordered = [
        {"id": items[1]["id"], "sort_order": 0},
        {"id": items[0]["id"], "sort_order": 1},
    ]
    rr = client.put(
        f"/api/v1/playlists/{playlist_id}/items/reorder",
        json=reordered,
    )
    assert rr.status_code == 200, rr.text
    w3 = client.get(f"/api/v1/watch/{token}")
    items3 = w3.json()["items"]
    assert items3[0]["id"] == items[1]["id"]

    # progress
    pr = client.put(
        f"/api/v1/watch/{token}/progress",
        json={"item_id": items3[0]["id"], "position_sec": 12.5},
    )
    assert pr.status_code == 200, pr.text
    w4 = client.get(f"/api/v1/watch/{token}")
    prog = w4.json()["progress"]
    assert prog and prog["item_id"] == items3[0]["id"]
    assert abs(prog["position_sec"] - 12.5) < 0.01

    # autoplay
    ap = client.put(
        f"/api/v1/watch/{token}/autoplay",
        json={"autoplay": True},
    )
    assert ap.status_code == 200
    assert ap.json()["autoplay"] is True
    assert client.get(f"/api/v1/watch/{token}").json()["autoplay"] is True

    # disable
    d = client.delete(f"/api/v1/playlists/{playlist_id}/share")
    assert d.status_code == 200
    assert client.get(f"/api/v1/watch/{token}").status_code == 404
    assert client.get(f"/watch/{token}").status_code == 404

    # cleanup
    client.delete(f"/api/v1/playlists/{playlist_id}")
    (media / "a.mp4").unlink(missing_ok=True)
    (media / "b.mp4").unlink(missing_ok=True)

    print("OK: playlist share/reorder/progress/autoplay")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
