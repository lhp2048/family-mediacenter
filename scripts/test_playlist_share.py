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

    listed = client.get(f"/api/v1/playlists/{playlist_id}")
    assert listed.status_code == 200, listed.text
    assert listed.json()["share_hide_completed"] is False
    assert listed.json()["share_hide_after"] == 1

    hidden = client.put(
        f"/api/v1/playlists/{playlist_id}/share/hide-completed",
        json={"enabled": True, "after": 1},
    )
    assert hidden.status_code == 200, hidden.text
    assert hidden.json()["share_hide_completed"] is True
    assert hidden.json()["share_hide_after"] == 1

    finished_id = items3[0]["id"]
    other_id = items3[1]["id"]
    done = client.post(
        f"/api/v1/watch/{token}/stats",
        json={"type": "complete", "item_id": finished_id},
    )
    assert done.status_code == 200, done.text
    mine = client.get(f"/api/v1/watch/{token}")
    assert mine.status_code == 200, mine.text
    mine_ids = [item["id"] for item in mine.json()["items"]]
    assert finished_id not in mine_ids, mine_ids
    assert other_id in mine_ids
    assert mine.json()["progress"] is None

    other = TestClient(app)
    theirs = other.get(f"/api/v1/watch/{token}")
    assert theirs.status_code == 200, theirs.text
    their_ids = [item["id"] for item in theirs.json()["items"]]
    assert finished_id in their_ids and other_id in their_ids

    opened = client.put(
        f"/api/v1/playlists/{playlist_id}/share/hide-completed",
        json={"enabled": False, "after": 1},
    )
    assert opened.status_code == 200, opened.text
    restored = [item["id"] for item in client.get(f"/api/v1/watch/{token}").json()["items"]]
    assert finished_id in restored and other_id in restored

    eye = client.get("/api/v1/share/eye-care")
    assert eye.status_code == 200, eye.text
    assert eye.json()["enabled"] is True
    assert eye.json()["play_minutes"] == 30
    assert eye.json()["rest_minutes"] == 15
    bad_eye = client.put(
        "/api/v1/share/eye-care",
        json={"enabled": True, "play_minutes": 0, "rest_minutes": 15},
    )
    assert bad_eye.status_code == 422, bad_eye.text
    try:
        tuned = client.put(
            "/api/v1/share/eye-care",
            json={"enabled": True, "play_minutes": 1, "rest_minutes": 1},
        )
        assert tuned.status_code == 200, tuned.text
        for _ in range(4):
            ticked = client.post(
                f"/api/v1/watch/{token}/stats",
                json={"type": "tick", "item_id": other_id, "delta_sec": 15},
            )
            assert ticked.status_code == 200, ticked.text
        assert ticked.json()["eye_rest"] is True
        resting = client.get(f"/api/v1/watch/{token}")
        assert resting.status_code == 200, resting.text
        assert resting.json()["eye_care"]["locked"] is True
        assert resting.json()["items"] == []
        blocked_media = client.get(f"/api/v1/watch/{token}/media/{other_id}")
        assert blocked_media.status_code == 403, blocked_media.text
        still_playing = other.get(f"/api/v1/watch/{token}")
        assert still_playing.json()["eye_care"]["locked"] is False
        assert other_id in [item["id"] for item in still_playing.json()["items"]]

        async def expire_rest() -> None:
            from datetime import timedelta

            from sqlalchemy import select

            from app.db import async_session
            from app.models.share_watch import ShareDeviceORM
            from app.services.share_watch import local_naive

            async with async_session() as session:
                device = (
                    await session.execute(
                        select(ShareDeviceORM).where(
                            ShareDeviceORM.visitor_token == client.cookies.get("fmc_visitor")
                        )
                    )
                ).scalar_one()
                device.eye_locked_until = local_naive() - timedelta(seconds=5)
                device.eye_watched_sec = 0
                device.eye_last_play_at = None
                await session.commit()

        asyncio.run(expire_rest())
        resumed = client.get(f"/api/v1/watch/{token}")
        assert resumed.json()["eye_care"]["locked"] is False
        assert other_id in [item["id"] for item in resumed.json()["items"]]

        async def almost_continuous() -> None:
            from datetime import timedelta

            from sqlalchemy import select

            from app.db import async_session
            from app.models.share_watch import ShareDeviceORM
            from app.services.share_watch import local_naive

            async with async_session() as session:
                device = (
                    await session.execute(
                        select(ShareDeviceORM).where(
                            ShareDeviceORM.visitor_token == client.cookies.get("fmc_visitor")
                        )
                    )
                ).scalar_one()
                device.eye_watched_sec = 50
                device.eye_last_play_at = local_naive() - timedelta(minutes=2)
                device.eye_locked_until = None
                await session.commit()

        asyncio.run(almost_continuous())
        reset = client.post(
            f"/api/v1/watch/{token}/stats",
            json={"type": "tick", "item_id": other_id, "delta_sec": 5},
        )
        assert reset.status_code == 200, reset.text
        assert reset.json()["eye_rest"] is False
        after_gap = client.get(f"/api/v1/watch/{token}").json()["eye_care"]
        assert after_gap["locked"] is False
        assert after_gap["watched_sec"] == 5

        off = client.put(
            "/api/v1/share/eye-care",
            json={"enabled": False, "play_minutes": 1, "rest_minutes": 1},
        )
        assert off.status_code == 200, off.text

        async def pile_up() -> None:
            from sqlalchemy import select

            from app.db import async_session
            from app.models.share_watch import ShareDeviceORM
            from app.services.share_watch import local_naive

            async with async_session() as session:
                device = (
                    await session.execute(
                        select(ShareDeviceORM).where(
                            ShareDeviceORM.visitor_token == client.cookies.get("fmc_visitor")
                        )
                    )
                ).scalar_one()
                device.eye_watched_sec = 100
                device.eye_last_play_at = local_naive()
                device.eye_locked_until = None
                await session.commit()

        asyncio.run(pile_up())
        ignored = client.post(
            f"/api/v1/watch/{token}/stats",
            json={"type": "tick", "item_id": other_id, "delta_sec": 15},
        )
        assert ignored.json()["eye_rest"] is False
        assert client.get(f"/api/v1/watch/{token}").json()["eye_care"]["locked"] is False
    finally:
        client.put(
            "/api/v1/share/eye-care",
            json={"enabled": True, "play_minutes": 30, "rest_minutes": 15},
        )

    # disable
    d = client.delete(f"/api/v1/playlists/{playlist_id}/share")
    assert d.status_code == 200
    assert client.get(f"/api/v1/watch/{token}").status_code == 404
    closed = client.get(f"/watch/{token}")
    assert closed.status_code == 200, closed.text
    assert "text/html" in closed.headers.get("content-type", "")
    assert "这个分享已暂停" in closed.text
    assert "detail" not in closed.text

    # cleanup
    client.delete(f"/api/v1/playlists/{playlist_id}")
    (media / "a.mp4").unlink(missing_ok=True)
    (media / "b.mp4").unlink(missing_ok=True)

    print("OK: playlist share/reorder/progress/autoplay")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
