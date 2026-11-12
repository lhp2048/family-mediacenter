#!/usr/bin/env python3
"""Ebook shelf and single-book share links."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    import asyncio

    from fastapi.testclient import TestClient

    from app.db import async_session, init_db
    from app.services.material_share import contain_path, material_share_service
    import app.services.material_service as material_service

    library = ROOT / "data" / "test-material-share"
    if library.exists():
        shutil.rmtree(library)
    story = library / "故事"
    nested = story / "下一层"
    nested.mkdir(parents=True)
    (story / "甲.txt").write_text("甲的正文", encoding="utf-8")
    (story / "meta.json").write_text(
        '{"title":"故事书架","author":"测试","description":"一套故事"}',
        encoding="utf-8",
    )
    (nested / "乙.txt").write_text("乙的正文", encoding="utf-8")
    (library / "其他.txt").write_text("不该看到", encoding="utf-8")

    material_service.get_materials_root = lambda: library
    asyncio.run(init_db())

    try:
        contain_path("故事", "../其他.txt")
        raise SystemExit("escape path should fail")
    except ValueError as exc:
        assert "超出" in str(exc), exc
    assert contain_path("故事", "下一层/乙.txt") == "故事/下一层/乙.txt"

    first = asyncio.run(material_share_service.enable("故事", "http://library.test"))
    second = asyncio.run(material_share_service.enable("故事", "http://library.test"))
    assert first.token == second.token
    assert first.is_dir is True
    assert first.share_url == f"http://library.test/shelf/{first.token}"

    book = asyncio.run(material_share_service.enable("故事/甲.txt", "http://library.test"))
    assert book.is_dir is False
    assert book.share_url.endswith(f"/book/{book.token}")

    asyncio.run(material_share_service.disable("故事"))
    try:
        asyncio.run(material_share_service.resolve_share(first.token))
        raise SystemExit("disabled share should fail")
    except ValueError as exc:
        assert "已停用" in str(exc)
    again = asyncio.run(material_share_service.enable("故事", "http://library.test"))
    assert again.token == first.token

    from app.main import app

    client = TestClient(app)
    token = again.token
    anon = TestClient(app)
    assert anon.get(f"/api/v1/shelf/{token}").status_code == 403

    page = client.get(f"/shelf/{token}")
    assert page.status_code == 200, page.text
    assert "故事书架" in page.text
    assert "甲.txt" in page.text

    shelf = client.get(f"/api/v1/shelf/{token}")
    assert shelf.status_code == 200, shelf.text
    body = shelf.json()
    assert body["name"] == "故事书架"
    names = [entry["name"] for entry in body["entries"]]
    assert "甲.txt" in names
    assert "下一层" in names
    assert "meta.json" not in names
    assert "/files/" not in shelf.text

    deeper = client.get(f"/api/v1/shelf/{token}", params={"path": "下一层"})
    assert deeper.status_code == 200, deeper.text
    assert [entry["name"] for entry in deeper.json()["entries"]] == ["乙.txt"]

    escaped = client.get(f"/api/v1/shelf/{token}", params={"path": "../其他.txt"})
    assert escaped.status_code == 400, escaped.text

    listed = shelf.json()["entries"]
    book_entry = next(entry for entry in listed if entry["name"] == "甲.txt")
    downloaded = client.get(book_entry["file_url"])
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.content == "甲的正文".encode("utf-8")

    book_file = client.get(f"/api/v1/book/{book.token}/file")
    assert book_file.status_code == 200
    assert book_file.content == "甲的正文".encode("utf-8")

    reading = client.get(f"/shelf/{token}/read", params={"path": "甲.txt"})
    assert reading.status_code == 200, reading.text
    assert "返回书架" in reading.text
    assert f"/api/v1/shelf/{token}/file" in reading.text
    assert "/files/" not in reading.text

    single = client.get(f"/book/{book.token}")
    assert single.status_code == 200, single.text
    assert "返回书架" not in single.text
    assert f"/api/v1/book/{book.token}/file" in single.text

    stopped = client.request(
        "DELETE",
        "/api/v1/materials/share",
        json={"sub_path": "故事"},
    )
    assert stopped.status_code == 200, stopped.text
    assert client.get(f"/shelf/{token}").status_code == 404
    assert client.get(book_entry["file_url"]).status_code == 404

    async def cleanup() -> None:
        from sqlalchemy import delete

        from app.models.material_share import MaterialShareORM
        from app.models.share_read import ShareReadORM, ShareReadVisitORM
        from app.models.share_watch import ShareDeviceORM
        from sqlalchemy import select

        visitor = client.cookies.get("fmc_visitor")
        async with async_session() as session:
            await session.execute(
                delete(MaterialShareORM).where(
                    MaterialShareORM.sub_path.in_(["故事", "故事/甲.txt"])
                )
            )
            if visitor:
                device_id = await session.scalar(
                    select(ShareDeviceORM.id).where(ShareDeviceORM.visitor_token == visitor)
                )
                if device_id is not None:
                    await session.execute(
                        delete(ShareReadORM).where(ShareReadORM.device_id == device_id)
                    )
                    await session.execute(
                        delete(ShareReadVisitORM).where(ShareReadVisitORM.device_id == device_id)
                    )
                    await session.execute(
                        delete(ShareDeviceORM).where(ShareDeviceORM.id == device_id)
                    )
            await session.commit()

    asyncio.run(cleanup())
    shutil.rmtree(library, ignore_errors=True)
    print("OK: material share")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
