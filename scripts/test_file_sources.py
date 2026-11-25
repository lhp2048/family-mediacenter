#!/usr/bin/env python3
"""Files page source switches between multimedia and the ebook library."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
import app.services.material_service as material_service  # noqa: E402


def main() -> int:
    library = ROOT / "data" / "test-file-sources"
    if library.exists():
        shutil.rmtree(library)
    books = library / "ebooks"
    (books / "故事").mkdir(parents=True)
    (books / "故事" / "甲.txt").write_text("正文", encoding="utf-8")
    (books / "故事" / "忽略.mp4").write_bytes(b"no")
    (books / "meta.json").write_text("{}", encoding="utf-8")
    original = material_service.get_materials_root
    material_service.get_materials_root = lambda: books
    try:
        with TestClient(app) as client:
            bad = client.get("/api/v1/files", params={"source": "pictures"})
            assert bad.status_code == 400, bad.text

            listed = client.get("/api/v1/files", params={"source": "ebooks"})
            assert listed.status_code == 200, listed.text
            body = listed.json()
            assert body["source"] == "ebooks"
            names = [item["name"] for item in body["entries"]]
            assert names == ["故事"], names

            inside = client.get("/api/v1/files", params={"source": "ebooks", "path": "故事"})
            assert inside.status_code == 200, inside.text
            files = {item["name"]: item for item in inside.json()["entries"]}
            assert "甲.txt" in files
            assert "忽略.mp4" not in files
            assert unquote(files["甲.txt"]["public_url"]).endswith("甲.txt")

            info = client.post(
                "/api/v1/files/info",
                json={"source": "ebooks", "paths": ["故事/甲.txt"]},
            )
            assert info.status_code == 200, info.text
            row = info.json()["items"][0]
            assert row["exists"] is True
            assert row["size"] == len("正文".encode("utf-8"))

            removed = client.delete(
                "/api/v1/files",
                params={"source": "ebooks", "path": "故事"},
            )
            assert removed.status_code == 200, removed.text
            assert not (books / "故事").exists()

            media = client.get("/api/v1/files", params={"source": "multimedia"})
            assert media.status_code == 200, media.text
            assert media.json()["source"] == "multimedia"
    finally:
        material_service.get_materials_root = original
        shutil.rmtree(library, ignore_errors=True)
    print("OK: file sources")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
