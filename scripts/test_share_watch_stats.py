#!/usr/bin/env python3
"""Share-page watch stats, device split, and allow switch."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

IPAD_UA = (
    "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
WINDOWS_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def main() -> int:
    import asyncio
    from datetime import date

    from app.services.share_watch import retention_cutoff

    assert retention_cutoff(date(2026, 11, 5)) == date(2026, 10, 5)
    assert retention_cutoff(date(2026, 3, 31)) == date(2026, 2, 28)
    assert retention_cutoff(date(2026, 1, 15)) == date(2025, 12, 15)

    from fastapi.testclient import TestClient

    from app.db import init_db
    from app.main import app
    from app.models.playlist import PlaylistCreate, PlaylistItemORM
    from app.services.playlist_service import playlist_service

    asyncio.run(init_db())

    async def seed():
        playlist = await playlist_service.create_playlist(PlaylistCreate(name="stats-smoke"))
        from app.db import async_session

        async with async_session() as session:
            session.add(
                PlaylistItemORM(
                    playlist_id=playlist.id,
                    rel_path="stats-a.mp4",
                    title="统计甲",
                    sort_order=0,
                )
            )
            await session.commit()
        return playlist.id

    playlist_id = asyncio.run(seed())
    media = ROOT / "downloads" / "multimedia"
    media.mkdir(parents=True, exist_ok=True)
    (media / "stats-a.mp4").write_bytes(b"fake-media")

    client_a = TestClient(app)
    client_b = TestClient(app)

    shared = client_a.post(f"/api/v1/playlists/{playlist_id}/share")
    assert shared.status_code == 200, shared.text
    token = shared.json()["share_token"]

    page = client_a.get(f"/watch/{token}", headers={"User-Agent": IPAD_UA})
    assert page.status_code == 200, page.text
    assert client_a.cookies.get("fmc_visitor")
    assert client_a.cookies.get("fmc_visit")

    page_b = client_b.get(f"/watch/{token}", headers={"User-Agent": WINDOWS_UA})
    assert page_b.status_code == 200, page_b.text
    assert client_b.cookies.get("fmc_visitor") != client_a.cookies.get("fmc_visitor")

    watch = client_a.get(f"/api/v1/watch/{token}", headers={"User-Agent": IPAD_UA})
    assert watch.status_code == 200, watch.text
    body = watch.json()
    assert body["allowed"] is True
    assert len(body["items"]) == 1, body
    item_id = body["items"][0]["id"]
    assert body["items"][0]["public_url"] == f"/api/v1/watch/{token}/media/{item_id}"

    media_ok = client_a.get(body["items"][0]["public_url"])
    assert media_ok.status_code == 200, media_ok.text
    assert media_ok.content == b"fake-media"

    played = client_a.post(
        f"/api/v1/watch/{token}/stats",
        json={"type": "play", "item_id": item_id},
    )
    assert played.status_code == 200, played.text
    ticked = client_a.post(
        f"/api/v1/watch/{token}/stats",
        json={"type": "tick", "item_id": item_id, "delta_sec": 5},
    )
    assert ticked.status_code == 200, ticked.text
    ignored = client_a.post(
        f"/api/v1/watch/{token}/stats",
        json={"type": "tick", "item_id": item_id, "delta_sec": 20},
    )
    assert ignored.status_code == 200, ignored.text
    assert ignored.json()["counted"] is False
    done = client_a.post(
        f"/api/v1/watch/{token}/stats",
        json={"type": "complete", "item_id": item_id},
    )
    assert done.status_code == 200, done.text

    from app.services.share_watch import local_naive, share_watch

    today = local_naive()
    today_text = today.date().isoformat()
    asyncio.run(
        share_watch.record_event(
            token,
            client_a.cookies.get("fmc_visitor"),
            int(client_a.cookies.get("fmc_visit")),
            "tick",
            item_id,
            4,
            at=today.replace(hour=10, minute=30, second=0, microsecond=0),
        )
    )
    asyncio.run(
        share_watch.record_event(
            token,
            client_a.cookies.get("fmc_visitor"),
            int(client_a.cookies.get("fmc_visit")),
            "tick",
            item_id,
            6,
            at=today.replace(hour=11, minute=10, second=0, microsecond=0),
        )
    )

    async def seed_old() -> None:
        from sqlalchemy import select

        from app.db import async_session
        from app.models.share_watch import ShareDeviceORM, SharePlaybackORM, ShareVisitORM

        async with async_session() as session:
            device = (
                await session.execute(
                    select(ShareDeviceORM).where(
                        ShareDeviceORM.visitor_token == client_a.cookies.get("fmc_visitor")
                    )
                )
            ).scalar_one()
            old_at = datetime(2026, 9, 1, 8, 0)
            visit = ShareVisitORM(
                device_id=device.id,
                playlist_id=playlist_id,
                started_at=old_at,
                last_seen_at=old_at,
                ip="192.168.1.9",
                user_agent="old",
                device_label=device.device_label,
            )
            session.add(visit)
            await session.flush()
            session.add(
                SharePlaybackORM(
                    visit_id=visit.id,
                    device_id=device.id,
                    playlist_id=playlist_id,
                    item_id=item_id,
                    title="过期",
                    day="2026-09-01",
                    hour=8,
                    watch_sec=99,
                    play_count=3,
                    complete_count=2,
                    first_played_at=old_at,
                    last_played_at=old_at,
                )
            )
            await session.commit()

    asyncio.run(seed_old())

    import app.api.routes as routes

    original_load = routes.load_settings

    def keyed():
        settings = original_load()
        settings.server.api_key = "stats-key"
        return settings

    routes.load_settings = keyed
    try:
        denied = client_a.get("/api/v1/share/stats")
        assert denied.status_code == 401, denied.text
        stats = client_a.get(
            "/api/v1/share/stats",
            params={"from": today_text, "to": today_text},
            headers={"X-API-Key": "stats-key"},
        )
    finally:
        routes.load_settings = original_load

    assert stats.status_code == 200, stats.text
    devices = stats.json()["devices"]

    async def device_id_for(visitor: str) -> int:
        from sqlalchemy import select

        from app.db import async_session
        from app.models.share_watch import ShareDeviceORM

        async with async_session() as session:
            result = await session.execute(
                select(ShareDeviceORM.id).where(ShareDeviceORM.visitor_token == visitor)
            )
            return int(result.scalar_one())

    ipad_id = asyncio.run(device_id_for(client_a.cookies.get("fmc_visitor")))
    windows_id = asyncio.run(device_id_for(client_b.cookies.get("fmc_visitor")))
    ipad = next(row for row in devices if row["id"] == ipad_id)
    windows = next(row for row in devices if row["id"] == windows_id)
    assert ipad["device_label"] == "iPad · Safari"
    assert windows["device_label"] == "Windows · Chrome"
    assert ipad["id"] != windows["id"]
    assert abs(ipad["watch_sec"] - 15) < 0.05, ipad
    assert windows["watch_sec"] == 0
    day = next(row for row in ipad["by_day"] if row["date"] == today_text)
    hours = {row["hour"]: row["watch_sec"] for row in day["hours"]}
    assert abs(hours.get(10, 0) - 4) < 0.05 or hours.get(10, 0) >= 4
    assert abs(hours.get(11, 0) - 6) < 0.05 or hours.get(11, 0) >= 6
    assert abs(sum(hours.values()) - 15) < 0.05, hours
    hot = ipad["hot_items"][0]
    assert hot["title"] == "统计甲"
    assert hot["play_count"] == 1
    assert hot["complete_count"] == 1
    assert ipad["allowed"] is True
    assert all(row["date"] != "2026-09-01" for row in ipad["by_day"])

    async def old_gone() -> None:
        from sqlalchemy import func, select

        from app.db import async_session
        from app.models.share_watch import ShareDeviceORM, SharePlaybackORM, ShareVisitORM

        async with async_session() as session:
            playbacks = await session.scalar(
                select(func.count()).select_from(SharePlaybackORM).where(
                    SharePlaybackORM.day == "2026-09-01"
                )
            )
            visits = await session.scalar(
                select(func.count()).select_from(ShareVisitORM).where(
                    ShareVisitORM.started_at < datetime(2026, 10, 1)
                )
            )
            device = await session.scalar(
                select(func.count()).select_from(ShareDeviceORM).where(
                    ShareDeviceORM.id == ipad_id
                )
            )
        assert playbacks == 0
        assert visits == 0
        assert device == 1

    asyncio.run(old_gone())

    bad_range = client_a.get(
        "/api/v1/share/stats",
        params={"from": "2026-11-06", "to": "2026-11-05"},
    )
    assert bad_range.status_code == 400, bad_range.text

    closed = client_a.put(
        f"/api/v1/share/devices/{ipad['id']}",
        json={"allowed": False},
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["allowed"] is False

    blocked = client_a.get(f"/api/v1/watch/{token}", headers={"User-Agent": IPAD_UA})
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["allowed"] is False
    assert blocked.json()["items"] == []
    media_blocked = client_a.get(f"/api/v1/watch/{token}/media/{item_id}")
    assert media_blocked.status_code == 403, media_blocked.text

    still = client_b.get(f"/api/v1/watch/{token}", headers={"User-Agent": WINDOWS_UA})
    assert still.status_code == 200
    assert still.json()["allowed"] is True
    assert len(still.json()["items"]) == 1

    client_a.delete(f"/api/v1/playlists/{playlist_id}")

    async def cleanup_devices() -> None:
        from sqlalchemy import delete

        from app.db import async_session
        from app.models.share_watch import ShareDeviceORM, SharePlaybackORM, ShareVisitORM

        async with async_session() as session:
            await session.execute(
                delete(SharePlaybackORM).where(SharePlaybackORM.device_id.in_([ipad_id, windows_id]))
            )
            await session.execute(
                delete(ShareVisitORM).where(ShareVisitORM.device_id.in_([ipad_id, windows_id]))
            )
            await session.execute(
                delete(ShareDeviceORM).where(ShareDeviceORM.id.in_([ipad_id, windows_id]))
            )
            await session.commit()

    asyncio.run(cleanup_devices())
    (media / "stats-a.mp4").unlink(missing_ok=True)
    print("OK: share watch stats")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
