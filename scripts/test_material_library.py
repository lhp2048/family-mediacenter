#!/usr/bin/env python3
"""Ebook library management: import, folders, rename, move, delete."""
from __future__ import annotations

import shutil
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from fastapi.testclient import TestClient

    from app.engines.aria2 import aria2_output_name
    from app.main import app
    from app.models.task import TaskResponse
    import app.services.material_library as material_library
    import app.services.material_service as material_service

    from app.services.task_manager import sanitize_download_options

    assert aria2_output_name(4, {"filename": "书.pdf", "preserve_filename": True}) == "书.pdf"
    assert aria2_output_name(4, {"filename": "书.pdf"}) == "task_4_书.pdf"
    assert aria2_output_name(4, {}) == "task_4"
    assert aria2_output_name(4, {"filename": "../../书.pdf", "preserve_filename": True}) == "task_4"
    assert aria2_output_name(4, {"filename": "a/b.pdf"}) == "task_4"
    assert sanitize_download_options(
        {"preserve_filename": True, "filename": "../x.pdf"}
    ) == {}
    kept = sanitize_download_options({"filename": "a.pdf"}, preserve_filename=True)
    assert kept == {"filename": "a.pdf", "preserve_filename": True}
    try:
        sanitize_download_options({"filename": "../a.pdf"}, preserve_filename=True)
        raise SystemExit("unsafe preserve name should fail")
    except ValueError as exc:
        assert "非法名称" in str(exc)

    library = ROOT / "data" / "test-material-library"
    if library.exists():
        shutil.rmtree(library)
    library.mkdir(parents=True)
    outside = library.parent / "test-material-library-outside.txt"
    outside.write_text("secret", encoding="utf-8")
    original_root = material_service.get_materials_root
    material_service.get_materials_root = lambda: library
    shelf = f"架{uuid.uuid4().hex[:8]}"

    captured: list = []

    async def fake_create(data, *, preserve_filename: bool = False):
        captured.append((data, preserve_filename))
        options = dict(data.options)
        if preserve_filename:
            options["preserve_filename"] = True
        return TaskResponse(
            id=7,
            url=data.url,
            source_type="aria2",
            status="pending",
            output_dir=data.output_dir or "",
            options=options,
        )

    material_library.task_manager.create_task = fake_create

    try:
        client = TestClient(app)

        created = client.post(
            "/api/v1/materials/folders", json={"path": f"{shelf}/下层"}
        )
        assert created.status_code == 200, created.text
        assert created.json()["path"] == f"{shelf}/下层"
        assert (library / shelf / "下层").is_dir()

        (library / "甲.txt").write_text("甲", encoding="utf-8")
        (library / shelf / "乙.txt").write_text("乙", encoding="utf-8")

        renamed = client.post(
            "/api/v1/materials/rename",
            json={"path": "甲.txt", "name": "丙.txt"},
        )
        assert renamed.status_code == 200, renamed.text
        assert renamed.json()["path"] == "丙.txt"
        assert (library / "丙.txt").read_text(encoding="utf-8") == "甲"

        bad_ext = client.post(
            "/api/v1/materials/rename",
            json={"path": "丙.txt", "name": "丙.exe"},
        )
        assert bad_ext.status_code == 400, bad_ext.text

        moved = client.post(
            "/api/v1/materials/move",
            json={"path": "丙.txt", "dest": shelf},
        )
        assert moved.status_code == 200, moved.text
        assert moved.json()["path"] == f"{shelf}/丙.txt"
        assert (library / shelf / "丙.txt").is_file()

        occupied = client.post(
            "/api/v1/materials/folders",
            json={"path": f"{shelf}/丙.txt"},
        )
        assert occupied.status_code == 409, occupied.text

        deeper = client.post(
            "/api/v1/materials/move",
            json={"path": f"{shelf}/丙.txt", "dest": f"{shelf}/下层"},
        )
        assert deeper.status_code == 200, deeper.text

        shared = client.post("/api/v1/materials/share", json={"sub_path": shelf})
        assert shared.status_code == 200, shared.text
        child = client.post(
            "/api/v1/materials/share",
            json={"sub_path": f"{shelf}/下层/丙.txt"},
        )
        assert child.status_code == 200, child.text
        token = shared.json()["token"]
        renamed_shelf = f"{shelf}新"

        renamed_dir = client.post(
            "/api/v1/materials/rename",
            json={"path": shelf, "name": renamed_shelf},
        )
        assert renamed_dir.status_code == 200, renamed_dir.text
        parent_share = client.get(
            "/api/v1/materials/share", params={"sub_path": renamed_shelf}
        )
        assert parent_share.status_code == 200, parent_share.text
        assert parent_share.json()["enabled"] is True
        assert parent_share.json()["token"] == token
        child_token = child.json()["token"]
        shelf_page = client.get(f"/shelf/{token}")
        assert shelf_page.status_code == 200, shelf_page.text
        assert renamed_shelf in shelf_page.text
        still_child = client.get(
            "/api/v1/materials/share",
            params={"sub_path": f"{renamed_shelf}/下层/丙.txt"},
        )
        assert still_child.json()["token"] == child_token
        child_share = client.get(
            "/api/v1/materials/share",
            params={"sub_path": f"{renamed_shelf}/下层/丙.txt"},
        )
        assert child_share.json()["enabled"] is True
        assert child_share.json()["sub_path"] == f"{renamed_shelf}/下层/丙.txt"

        removed = client.delete("/api/v1/materials", params={"path": renamed_shelf})
        assert removed.status_code == 200, removed.text
        assert not (library / renamed_shelf).exists()
        stopped = client.get(
            "/api/v1/materials/share", params={"sub_path": renamed_shelf}
        )
        assert stopped.json()["enabled"] is False
        nested = client.get(
            "/api/v1/materials/share",
            params={"sub_path": f"{renamed_shelf}/下层/丙.txt"},
        )
        assert nested.json()["enabled"] is False

        missing = client.delete("/api/v1/materials", params={"path": "没有这本书.pdf"})
        assert missing.status_code == 404, missing.text

        link = library / "leak.txt"
        link.symlink_to(outside)
        renamed_link = client.post(
            "/api/v1/materials/rename",
            json={"path": "leak.txt", "name": "ok.txt"},
        )
        assert renamed_link.status_code == 400, renamed_link.text
        assert link.is_symlink()
        assert outside.read_text(encoding="utf-8") == "secret"
        leaked = client.delete("/api/v1/materials", params={"path": "leak.txt"})
        assert leaked.status_code == 200, leaked.text
        assert not link.exists()
        assert outside.read_text(encoding="utf-8") == "secret"

        root_delete = client.delete("/api/v1/materials", params={"path": "."})
        assert root_delete.status_code == 400, root_delete.text
        assert library.is_dir()

        blocker = library / f"文件{shelf}.txt"
        blocker.write_text("x", encoding="utf-8")
        nested_file = client.post(
            "/api/v1/materials/folders",
            json={"path": f"文件{shelf}.txt/子"},
        )
        assert nested_file.status_code == 409, nested_file.text

        holder = f"占位{shelf}.txt"
        replacement = f"替补{shelf}.txt"
        (library / holder).write_text("a", encoding="utf-8")
        held = client.post("/api/v1/materials/share", json={"sub_path": holder})
        assert held.status_code == 200, held.text
        cleared = client.delete("/api/v1/materials", params={"path": holder})
        assert cleared.status_code == 200, cleared.text
        (library / replacement).write_text("b", encoding="utf-8")
        moved_share = client.post(
            "/api/v1/materials/share", json={"sub_path": replacement}
        )
        assert moved_share.status_code == 200, moved_share.text
        taken = client.post(
            "/api/v1/materials/rename",
            json={"path": replacement, "name": holder},
        )
        assert taken.status_code == 200, taken.text
        assert (library / holder).read_text(encoding="utf-8") == "b"
        reused = client.get("/api/v1/materials/share", params={"sub_path": holder})
        assert reused.json()["enabled"] is True
        assert reused.json()["token"] == moved_share.json()["token"]

        (library / "已有.pdf").write_bytes(b"%PDF")
        duplicate = client.post(
            "/api/v1/materials/import",
            json={"url": "https://example.com/已有.pdf", "filename": "已有.pdf"},
        )
        assert duplicate.status_code == 409, duplicate.text
        assert captured == []

        webpage = client.post(
            "/api/v1/materials/import",
            json={"url": "https://example.com/read", "sub_path": ""},
        )
        assert webpage.status_code == 400, webpage.text

        imported = client.post(
            "/api/v1/materials/import",
            json={
                "url": "请下载 https://cdn.example.com/books/海洋.pdf?dl=1",
                "sub_path": "",
            },
        )
        assert imported.status_code == 200, imported.text
        body = imported.json()
        assert body["id"] == 7
        assert body["source_type"] == "aria2"
        created_task, preserve = captured[0]
        assert preserve is True
        assert "preserve_filename" not in created_task.options
        assert created_task.url == "https://cdn.example.com/books/海洋.pdf?dl=1"
        assert created_task.engine == "aria2"
        assert created_task.options["filename"] == "海洋.pdf"
        assert Path(created_task.output_dir) == library.resolve()

        import asyncio

        from app.db import async_session
        from app.engines.base import serialize_options
        from app.models.material_share import MaterialShareORM
        from app.models.task import TaskORM

        async def seed_reserved() -> None:
            async with async_session() as session:
                session.add(
                    TaskORM(
                        url=f"https://example.com/{shelf}.pdf",
                        source_type="aria2",
                        status="paused",
                        options_json=serialize_options(
                            {"filename": "排队.pdf", "preserve_filename": True}
                        ),
                        output_dir=str(library.resolve()),
                    )
                )
                await session.commit()

        asyncio.run(seed_reserved())
        queued = client.post(
            "/api/v1/materials/import",
            json={"url": "https://example.com/queued.pdf", "filename": "排队.pdf"},
        )
        assert queued.status_code == 409, queued.text
        assert len(captured) == 1

        print("OK: material library management")
        return 0
    finally:
        material_service.get_materials_root = original_root

        async def cleanup_rows() -> None:
            from sqlalchemy import delete as sql_delete
            from sqlalchemy import select

            from app.db import async_session
            from app.models.material_share import MaterialShareORM
            from app.models.task import TaskORM

            async with async_session() as session:
                shares = (await session.execute(select(MaterialShareORM))).scalars().all()
                for row in shares:
                    if shelf in (row.sub_path or ""):
                        await session.delete(row)
                await session.execute(
                    sql_delete(TaskORM).where(
                        TaskORM.url == f"https://example.com/{shelf}.pdf"
                    )
                )
                await session.commit()

        import asyncio

        asyncio.run(cleanup_rows())
        link = library / "leak.txt"
        if link.is_symlink():
            link.unlink()
        shutil.rmtree(library, ignore_errors=True)
        outside.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
