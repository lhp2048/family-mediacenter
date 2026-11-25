#!/usr/bin/env python3
"""Upload an ebook into the library and a video into a playlist."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from fastapi.testclient import TestClient

    from app.main import app
    import app.api.playlists as playlists_api
    import app.services.file_manager as file_manager
    import app.services.material_service as material_service
    import app.utils.media as media

    library = ROOT / "data" / "test-local-upload"
    if library.exists():
        shutil.rmtree(library)
    books = library / "ebooks"
    media_dir = library / "multimedia"
    books.mkdir(parents=True)
    media_dir.mkdir()
    original_materials = material_service.get_materials_root
    original_download = file_manager.get_download_root
    original_playlist_download = playlists_api.get_download_root
    material_service.get_materials_root = lambda: books
    file_manager.get_download_root = lambda: media_dir
    media.get_download_root = lambda: media_dir
    playlists_api.get_download_root = lambda: media_dir

    try:
        client = TestClient(app)

        created = client.post(
            "/api/v1/materials/upload",
            files={"file": ("故事.txt", "你好".encode("utf-8"), "text/plain")},
            data={"sub_path": ""},
        )
        assert created.status_code == 200, created.text
        assert created.json()["path"] == "故事.txt"
        assert (books / "故事.txt").read_text(encoding="utf-8") == "你好"

        duplicate = client.post(
            "/api/v1/materials/upload",
            files={"file": ("故事.txt", b"again", "text/plain")},
        )
        assert duplicate.status_code == 409, duplicate.text
        assert (books / "故事.txt").read_text(encoding="utf-8") == "你好"

        rejected = client.post(
            "/api/v1/materials/upload",
            files={"file": ("病毒.exe", b"no", "application/octet-stream")},
        )
        assert rejected.status_code == 400, rejected.text
        assert not (books / "病毒.exe").exists()

        playlists = client.get("/api/v1/playlists")
        assert playlists.status_code == 200, playlists.text
        default = next(item for item in playlists.json() if item.get("is_default"))
        uploaded = client.post(
            f"/api/v1/playlists/{default['id']}/upload",
            files={"file": ("clip.mp4", b"\x00\x00clip", "video/mp4")},
        )
        assert uploaded.status_code == 200, uploaded.text
        uploaded_item = uploaded.json()
        assert uploaded_item["rel_path"].endswith("clip.mp4")
        assert (media_dir / "clip.mp4").read_bytes() == b"\x00\x00clip"

        listed = client.get(f"/api/v1/playlists/{default['id']}/items", params={"probe": "false"})
        assert listed.status_code == 200, listed.text
        names = [item["rel_path"] for item in listed.json()]
        assert any(name.endswith("clip.mp4") for name in names), names

        not_media = client.post(
            f"/api/v1/playlists/{default['id']}/upload",
            files={"file": ("note.pdf", b"%PDF", "application/pdf")},
        )
        assert not_media.status_code == 400, not_media.text
        assert not (media_dir / "note.pdf").exists()
        removed = client.delete(
            f"/api/v1/playlists/{default['id']}/items/{uploaded_item['id']}"
        )
        assert removed.status_code == 200, removed.text

        print("OK: local upload")
        return 0
    finally:
        material_service.get_materials_root = original_materials
        file_manager.get_download_root = original_download
        media.get_download_root = original_download
        playlists_api.get_download_root = original_playlist_download
        shutil.rmtree(library, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
