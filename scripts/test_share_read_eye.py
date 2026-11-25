#!/usr/bin/env python3
"""Ebook shares use the same per-device eye-care limit as video."""
from __future__ import annotations

import shutil
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    import asyncio

    from fastapi.testclient import TestClient
    from sqlalchemy import delete, select

    from app.config import load_settings
    from app.db import async_session, init_db
    from app.main import app
    from app.models.material_share import MaterialShareORM
    from app.models.share_read import ShareReadORM, ShareReadVisitORM
    from app.models.share_watch import ShareDeviceORM
    import app.services.material_service as material_service

    library = ROOT / "data" / "test-read-eye"
    if library.exists():
        shutil.rmtree(library)
    folder = f"护眼{uuid.uuid4().hex[:8]}"
    story = library / folder
    story.mkdir(parents=True)
    (story / "甲.txt").write_text("甲的正文", encoding="utf-8")
    material_service.get_materials_root = lambda: library

    asyncio.run(init_db())
    settings = load_settings()
    headers = {"X-API-Key": settings.server.api_key} if settings.server.api_key else {}
    visitor_tokens: list[str] = []
    share_paths = [folder, f"{folder}/甲.txt"]

    async def restore_eye() -> None:
        from app.services.share_watch import share_watch

        await share_watch.set_eye_care(True, 30, 15)

    try:
        from app.services.material_share import material_share_service

        shelf = asyncio.run(material_share_service.enable(folder, "http://library.test"))
        book = asyncio.run(
            material_share_service.enable(f"{folder}/甲.txt", "http://library.test")
        )

        client = TestClient(app)
        page = client.get(
            f"/shelf/{shelf.token}/read",
            params={"path": "甲.txt"},
        )
        assert page.status_code == 200, page.text
        assert "eye_rest" in page.text
        visit_id = int(client.cookies.get("fmc_read_visit"))
        visitor = client.cookies.get("fmc_visitor")
        assert visitor
        visitor_tokens.append(visitor)

        tuned = client.put(
            "/api/v1/share/eye-care",
            headers=headers,
            json={"enabled": True, "play_minutes": 1, "rest_minutes": 1},
        )
        assert tuned.status_code == 200, tuned.text

        last = None
        for _ in range(4):
            last = client.post(
                f"/api/v1/share/read/{shelf.token}/stats",
                json={"type": "tick", "visit_id": visit_id, "delta_sec": 15},
            )
            assert last.status_code == 200, last.text
        assert last is not None
        assert last.json()["counted"] is True
        assert last.json()["eye_rest"] is True
        assert last.json()["rest_remaining_sec"] >= 1

        blocked = client.post(
            f"/api/v1/share/read/{shelf.token}/stats",
            json={"type": "tick", "visit_id": visit_id, "delta_sec": 5},
        )
        assert blocked.status_code == 200, blocked.text
        assert blocked.json()["counted"] is False
        assert blocked.json()["eye_rest"] is True

        shelf_file = client.get(
            f"/api/v1/shelf/{shelf.token}/file",
            params={"path": "甲.txt"},
        )
        assert shelf_file.status_code == 403, shelf_file.text
        assert shelf_file.json()["detail"] == "该休息一下"
        book_file = client.get(f"/api/v1/book/{book.token}/file")
        assert book_file.status_code == 403, book_file.text

        resting_shelf = client.get(f"/shelf/{shelf.token}")
        assert resting_shelf.status_code == 200, resting_shelf.text
        assert "该休息了" in resting_shelf.text
        assert "甲.txt" not in resting_shelf.text
        resting_read = client.get(
            f"/shelf/{shelf.token}/read",
            params={"path": "甲.txt"},
        )
        assert resting_read.status_code == 200, resting_read.text
        assert "该休息了" in resting_read.text
        assert f"/api/v1/shelf/{shelf.token}/file" not in resting_read.text
        resting_book = client.get(f"/book/{book.token}")
        assert resting_book.status_code == 200, resting_book.text
        assert "该休息了" in resting_book.text
        assert f"/api/v1/book/{book.token}/file" not in resting_book.text

        other = TestClient(app)
        other_shelf = other.get(f"/shelf/{shelf.token}")
        assert other_shelf.status_code == 200, other_shelf.text
        assert "甲.txt" in other_shelf.text
        assert "该休息了" not in other_shelf.text
        other_file = other.get(
            f"/api/v1/shelf/{shelf.token}/file",
            params={"path": "甲.txt"},
        )
        assert other_file.status_code == 200, other_file.text
        other_visitor = other.cookies.get("fmc_visitor")
        if other_visitor:
            visitor_tokens.append(other_visitor)

        async def visitor_device_id(token: str) -> int:
            async with async_session() as session:
                device = (
                    await session.execute(
                        select(ShareDeviceORM).where(ShareDeviceORM.visitor_token == token)
                    )
                ).scalar_one()
                return int(device.id)

        device_id = asyncio.run(visitor_device_id(visitor))
        status = client.get("/api/v1/share/eye-care/status", headers=headers)
        assert status.status_code == 200, status.text
        body = status.json()
        assert body["enabled"] is True
        assert body["play_minutes"] == 1
        assert body["rest_minutes"] == 1
        mine = next(row for row in body["devices"] if row["id"] == device_id)
        assert mine["locked"] is True
        assert mine["rest_remaining_sec"] >= 1
        assert mine["watched_sec"] == 0
        other_id = asyncio.run(visitor_device_id(other_visitor))
        other_row = next(row for row in body["devices"] if row["id"] == other_id)
        assert other_row["locked"] is False

        missing = client.post(
            "/api/v1/share/eye-care/devices/0/reset",
            headers=headers,
        )
        assert missing.status_code == 404, missing.text
        reset = client.post(
            f"/api/v1/share/eye-care/devices/{device_id}/reset",
            headers=headers,
        )
        assert reset.status_code == 200, reset.text
        assert reset.json()["id"] == device_id
        assert reset.json()["locked"] is False
        assert reset.json()["watched_sec"] == 0
        released = client.get(
            f"/api/v1/shelf/{shelf.token}/file",
            params={"path": "甲.txt"},
        )
        assert released.status_code == 200, released.text
        after = client.get("/api/v1/share/eye-care/status", headers=headers)
        again = next(row for row in after.json()["devices"] if row["id"] == device_id)
        assert again["locked"] is False

        async def expire_rest() -> None:
            from datetime import timedelta

            from app.services.share_watch import local_naive

            async with async_session() as session:
                device = (
                    await session.execute(
                        select(ShareDeviceORM).where(
                            ShareDeviceORM.visitor_token == visitor
                        )
                    )
                ).scalar_one()
                device.eye_locked_until = local_naive() - timedelta(seconds=5)
                device.eye_watched_sec = 0
                device.eye_last_play_at = None
                await session.commit()

        asyncio.run(expire_rest())
        resumed = client.get(
            f"/api/v1/shelf/{shelf.token}/file",
            params={"path": "甲.txt"},
        )
        assert resumed.status_code == 200, resumed.text
        resumed_page = client.get(f"/shelf/{shelf.token}")
        assert "甲.txt" in resumed_page.text
        assert "该休息了" not in resumed_page.text

        async def almost_continuous() -> None:
            from datetime import timedelta

            from app.services.share_watch import local_naive

            async with async_session() as session:
                device = (
                    await session.execute(
                        select(ShareDeviceORM).where(
                            ShareDeviceORM.visitor_token == visitor
                        )
                    )
                ).scalar_one()
                device.eye_watched_sec = 50
                device.eye_last_play_at = local_naive() - timedelta(minutes=2)
                device.eye_locked_until = None
                await session.commit()

        asyncio.run(almost_continuous())
        reset = client.post(
            f"/api/v1/share/read/{shelf.token}/stats",
            json={"type": "tick", "visit_id": visit_id, "delta_sec": 5},
        )
        assert reset.status_code == 200, reset.text
        assert reset.json()["eye_rest"] is False

        async def watched_after_gap() -> float:
            async with async_session() as session:
                device = (
                    await session.execute(
                        select(ShareDeviceORM).where(
                            ShareDeviceORM.visitor_token == visitor
                        )
                    )
                ).scalar_one()
                return float(device.eye_watched_sec or 0)

        assert asyncio.run(watched_after_gap()) == 5

        off = client.put(
            "/api/v1/share/eye-care",
            headers=headers,
            json={"enabled": False, "play_minutes": 1, "rest_minutes": 1},
        )
        assert off.status_code == 200, off.text

        async def pile_up() -> None:
            from app.services.share_watch import local_naive

            async with async_session() as session:
                device = (
                    await session.execute(
                        select(ShareDeviceORM).where(
                            ShareDeviceORM.visitor_token == visitor
                        )
                    )
                ).scalar_one()
                device.eye_watched_sec = 100
                device.eye_last_play_at = local_naive()
                device.eye_locked_until = None
                await session.commit()

        asyncio.run(pile_up())
        ignored = client.post(
            f"/api/v1/share/read/{shelf.token}/stats",
            json={"type": "tick", "visit_id": visit_id, "delta_sec": 15},
        )
        assert ignored.json()["eye_rest"] is False
        still_open = client.get(
            f"/api/v1/book/{book.token}/file",
        )
        assert still_open.status_code == 200, still_open.text
    finally:
        asyncio.run(restore_eye())

        async def cleanup() -> None:
            async with async_session() as session:
                devices = (
                    await session.execute(
                        select(ShareDeviceORM).where(
                            ShareDeviceORM.visitor_token.in_(visitor_tokens)
                        )
                    )
                ).scalars().all() if visitor_tokens else []
                device_ids = [row.id for row in devices]
                if device_ids:
                    await session.execute(
                        delete(ShareReadORM).where(ShareReadORM.device_id.in_(device_ids))
                    )
                    await session.execute(
                        delete(ShareReadVisitORM).where(
                            ShareReadVisitORM.device_id.in_(device_ids)
                        )
                    )
                    await session.execute(
                        delete(ShareDeviceORM).where(ShareDeviceORM.id.in_(device_ids))
                    )
                await session.execute(
                    delete(MaterialShareORM).where(
                        MaterialShareORM.sub_path.in_(share_paths)
                    )
                )
                await session.commit()

        asyncio.run(cleanup())
        if library.exists():
            shutil.rmtree(library)
    print("OK: share read eye care")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
