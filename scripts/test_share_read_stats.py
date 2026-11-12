#!/usr/bin/env python3
"""Share-page ebook reading stats."""
from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

IPAD_UA = (
    "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)


def main() -> int:
    import asyncio

    from fastapi.testclient import TestClient
    from sqlalchemy import delete, func, select

    from app.db import async_session, init_db
    from app.main import app
    from app.models.material_share import MaterialShareORM
    from app.models.playlist import PlaylistCreate, PlaylistItemORM
    from app.models.share_read import ShareReadORM, ShareReadVisitORM
    from app.models.share_watch import ShareDeviceORM, SharePlaybackORM, ShareVisitORM
    from app.services.playlist_service import playlist_service
    from app.services.share_read import share_read
    from app.services.share_watch import share_watch
    import app.services.material_service as material_service

    library = ROOT / "data" / "test-read-stats"
    if library.exists():
        shutil.rmtree(library)
    story = library / "故事"
    story.mkdir(parents=True)
    (story / "甲.txt").write_text("甲的正文", encoding="utf-8")
    (story / "乙.txt").write_text("乙的正文", encoding="utf-8")
    material_service.get_materials_root = lambda: library

    asyncio.run(init_db())
    playlist_id = 0
    device_ids: list[int] = []
    try:
        async def seed_playlist():
            playlist = await playlist_service.create_playlist(PlaylistCreate(name="read-stats-smoke"))
            async with async_session() as session:
                session.add(
                    PlaylistItemORM(
                        playlist_id=playlist.id,
                        rel_path="read-stats-a.mp4",
                        title="阅读统计片",
                        sort_order=0,
                    )
                )
                await session.commit()
            return playlist.id

        playlist_id = asyncio.run(seed_playlist())
        media = ROOT / "downloads" / "multimedia"
        media.mkdir(parents=True, exist_ok=True)
        (media / "read-stats-a.mp4").write_bytes(b"fake-media")

        from app.services.material_share import material_share_service

        shelf = asyncio.run(material_share_service.enable("故事", "http://library.test"))
        book = asyncio.run(material_share_service.enable("故事/甲.txt", "http://library.test"))

        client = TestClient(app)
        shared = client.post(f"/api/v1/playlists/{playlist_id}/share")
        assert shared.status_code == 200, shared.text
        watch_token = shared.json()["share_token"]
        watch_page = client.get(f"/watch/{watch_token}", headers={"User-Agent": IPAD_UA})
        assert watch_page.status_code == 200, watch_page.text
        visitor = client.cookies.get("fmc_visitor")
        video_visit = client.cookies.get("fmc_visit")
        assert visitor
        assert video_visit

        shelf_page = client.get(f"/shelf/{shelf.token}")
        assert shelf_page.status_code == 200, shelf_page.text
        assert "/api/v1/share/read/" not in shelf_page.text
        assert client.cookies.get("fmc_visit") == video_visit

        embed = client.get("/materials/embed", params={"path": "故事/甲.txt"})
        assert embed.status_code == 200, embed.text
        assert "/api/v1/share/read/" not in embed.text

        read_page = client.get(
            f"/shelf/{shelf.token}/read",
            params={"path": "甲.txt"},
            headers={"User-Agent": IPAD_UA},
        )
        assert read_page.status_code == 200, read_page.text
        assert "/api/v1/share/read/" in read_page.text
        assert "visit_id" in read_page.text
        assert "甲.txt" in read_page.text
        assert client.cookies.get("fmc_visitor") == visitor
        assert client.cookies.get("fmc_visit") == video_visit
        visit_jia = int(client.cookies.get("fmc_read_visit"))

        other = client.get(
            f"/shelf/{shelf.token}/read",
            params={"path": "乙.txt"},
            headers={"User-Agent": IPAD_UA},
        )
        assert other.status_code == 200, other.text
        visit_yi = int(client.cookies.get("fmc_read_visit"))
        assert visit_yi != visit_jia

        book_page = client.get(f"/book/{book.token}", headers={"User-Agent": IPAD_UA})
        assert book_page.status_code == 200, book_page.text
        assert "/api/v1/share/read/" in book_page.text
        assert "visit_id" in book_page.text

        async def one_device() -> int:
            async with async_session() as session:
                rows = (
                    await session.execute(
                        select(ShareDeviceORM).where(ShareDeviceORM.visitor_token == visitor)
                    )
                ).scalars().all()
            assert len(rows) == 1
            return rows[0].id

        device_id = asyncio.run(one_device())
        device_ids.append(device_id)

        opened_other = client.post(
            f"/api/v1/share/read/{shelf.token}/stats",
            json={"type": "open", "visit_id": visit_yi},
        )
        assert opened_other.status_code == 200, opened_other.text
        assert opened_other.json()["counted"] is True
        opened = client.post(
            f"/api/v1/share/read/{shelf.token}/stats",
            json={"type": "open", "visit_id": visit_jia},
        )
        assert opened.status_code == 200, opened.text
        assert opened.json()["counted"] is True
        again = client.post(
            f"/api/v1/share/read/{shelf.token}/stats",
            json={"type": "open", "visit_id": visit_jia},
        )
        assert again.status_code == 200, again.text
        assert again.json()["counted"] is False
        ignored = client.post(
            f"/api/v1/share/read/{shelf.token}/stats",
            json={"type": "tick", "delta_sec": 20, "visit_id": visit_jia},
        )
        assert ignored.status_code == 200, ignored.text
        assert ignored.json()["counted"] is False
        moved = client.post(
            f"/api/v1/share/read/{shelf.token}/stats",
            json={"type": "tick", "delta_sec": 5, "visit_id": visit_jia},
        )
        assert moved.status_code == 200, moved.text
        assert moved.json()["counted"] is True

        from app.services.share_watch import local_naive

        today = local_naive()
        day_key = today.date().isoformat()
        asyncio.run(
            share_read.record_event(
                shelf.token,
                visitor,
                visit_jia,
                "tick",
                4,
                at=today.replace(hour=10, minute=30, second=0, microsecond=0),
            )
        )
        asyncio.run(
            share_read.record_event(
                shelf.token,
                visitor,
                visit_jia,
                "tick",
                6,
                at=today.replace(hour=11, minute=10, second=0, microsecond=0),
            )
        )
        book_open = client.post(
            f"/api/v1/share/read/{book.token}/stats",
            json={"type": "open"},
        )
        assert book_open.status_code == 200, book_open.text
        assert book_open.json()["counted"] is True

        from datetime import timedelta

        old_date = today.date() - timedelta(days=40)
        old_at = datetime(old_date.year, old_date.month, old_date.day, 8, 0)
        old_key = old_date.isoformat()

        async def seed_old() -> None:
            async with async_session() as session:
                visit = ShareReadVisitORM(
                    device_id=device_id,
                    token=shelf.token,
                    book_path="故事/旧.txt",
                    title="旧.txt",
                    started_at=old_at,
                    last_seen_at=old_at,
                    device_label="iPad · Safari",
                    opened=True,
                )
                session.add(visit)
                await session.flush()
                session.add(
                    ShareReadORM(
                        visit_id=visit.id,
                        device_id=device_id,
                        token=shelf.token,
                        book_path="故事/旧.txt",
                        title="旧.txt",
                        day=old_key,
                        hour=8,
                        read_sec=99,
                        open_count=2,
                        first_read_at=old_at,
                        last_read_at=old_at,
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
            denied = client.get("/api/v1/share/read-stats")
            assert denied.status_code == 401, denied.text
            stats = client.get(
                "/api/v1/share/read-stats",
                params={"from": day_key, "to": day_key},
                headers={"X-API-Key": "stats-key"},
            )
        finally:
            routes.load_settings = original_load

        assert stats.status_code == 200, stats.text
        row = next(item for item in stats.json()["devices"] if item["id"] == device_id)
        assert row["device_label"] == "iPad · Safari"
        assert row["allowed"] is True
        assert abs(row["read_sec"] - 15) < 0.05, row
        day = next(item for item in row["by_day"] if item["date"] == day_key)
        hours = {item["hour"]: item["read_sec"] for item in day["hours"]}
        extra_10 = 5 if today.hour == 10 else 0
        extra_11 = 5 if today.hour == 11 else 0
        assert abs(hours.get(10, 0) - (4 + extra_10)) < 0.05, hours
        assert abs(hours.get(11, 0) - (6 + extra_11)) < 0.05, hours
        assert abs(sum(hours.values()) - 15) < 0.05, hours
        by_path = {item["path"]: item for item in row["hot_books"]}
        assert by_path["故事/甲.txt"]["title"] == "甲.txt"
        assert by_path["故事/甲.txt"]["open_count"] == 2
        assert abs(by_path["故事/甲.txt"]["read_sec"] - 15) < 0.05
        assert by_path["故事/乙.txt"]["open_count"] == 1
        assert by_path["故事/乙.txt"]["read_sec"] == 0
        assert all(item["date"] != old_key for item in row["by_day"])

        async def old_gone() -> None:
            async with async_session() as session:
                reads = await session.scalar(
                    select(func.count()).select_from(ShareReadORM).where(
                        ShareReadORM.device_id == device_id,
                        ShareReadORM.day == old_key,
                    )
                )
                visits = await session.scalar(
                    select(func.count()).select_from(ShareReadVisitORM).where(
                        ShareReadVisitORM.device_id == device_id,
                        ShareReadVisitORM.book_path == "故事/旧.txt",
                    )
                )
                device = await session.get(ShareDeviceORM, device_id)
            assert reads == 0
            assert visits == 0
            assert device is not None

        asyncio.run(old_gone())

        bad_range = client.get(
            "/api/v1/share/read-stats",
            params={"from": "2026-11-06", "to": "2026-11-05"},
        )
        assert bad_range.status_code == 400, bad_range.text

        asyncio.run(share_watch.set_allowed(device_id, False))
        blocked = client.get(
            f"/shelf/{shelf.token}/read",
            params={"path": "甲.txt"},
            headers={"User-Agent": IPAD_UA},
        )
        assert blocked.status_code == 200, blocked.text
        assert "这台设备未允许" in blocked.text
        assert "甲.txt" not in blocked.text
        blocked_shelf = client.get(f"/shelf/{shelf.token}")
        assert "这台设备未允许" in blocked_shelf.text
        assert "甲.txt" not in blocked_shelf.text
        blocked_file = client.get(
            f"/api/v1/shelf/{shelf.token}/file",
            params={"path": "甲.txt"},
        )
        assert blocked_file.status_code == 403, blocked_file.text
        still = client.post(
            f"/api/v1/share/read/{shelf.token}/stats",
            json={"type": "open", "visit_id": visit_jia},
        )
        assert still.status_code == 403, still.text
    finally:
        async def cleanup() -> None:
            async with async_session() as session:
                if device_ids:
                    await session.execute(
                        delete(ShareReadORM).where(ShareReadORM.device_id.in_(device_ids))
                    )
                    await session.execute(
                        delete(ShareReadVisitORM).where(ShareReadVisitORM.device_id.in_(device_ids))
                    )
                    await session.execute(
                        delete(SharePlaybackORM).where(SharePlaybackORM.device_id.in_(device_ids))
                    )
                    await session.execute(
                        delete(ShareVisitORM).where(ShareVisitORM.device_id.in_(device_ids))
                    )
                    await session.execute(
                        delete(ShareDeviceORM).where(ShareDeviceORM.id.in_(device_ids))
                    )
                await session.execute(
                    delete(MaterialShareORM).where(
                        MaterialShareORM.sub_path.in_(["故事", "故事/甲.txt"])
                    )
                )
                await session.commit()

        asyncio.run(cleanup())
        if playlist_id:
            try:
                asyncio.run(playlist_service.delete_playlist(playlist_id))
            except Exception:
                pass
        media_file = ROOT / "downloads" / "multimedia" / "read-stats-a.mp4"
        if media_file.exists():
            media_file.unlink()
        if library.exists():
            shutil.rmtree(library)
    print("OK: share read stats")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
