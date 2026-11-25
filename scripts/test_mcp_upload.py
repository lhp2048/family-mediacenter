#!/usr/bin/env python3
"""MCP local-file upload helpers against the media center app."""
from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "mcp_server"))


def main() -> int:
    return asyncio.run(run())


async def run() -> int:
    import httpx

    from app.main import app
    from uploads import post_local_file, resolve_local_file
    import app.api.playlists as playlists_api
    import app.services.file_manager as file_manager
    import app.services.material_service as material_service
    import app.utils.media as media

    library = ROOT / "data" / "test-mcp-upload"
    if library.exists():
        shutil.rmtree(library)
    books = library / "ebooks"
    media_dir = library / "multimedia"
    books.mkdir(parents=True)
    media_dir.mkdir()
    source = library / "本机故事.txt"
    source.write_text("正文", encoding="utf-8")
    video = library / "本机片段.mp4"
    video.write_bytes(b"\x00\x00clip")

    try:
        resolve_local_file(str(source))
        try:
            resolve_local_file(str(library / "没有.txt"))
            raise SystemExit("missing file should fail")
        except ValueError as exc:
            assert "不存在" in str(exc)

        original_materials = material_service.get_materials_root
        original_download = file_manager.get_download_root
        original_playlist_download = playlists_api.get_download_root
        material_service.get_materials_root = lambda: books
        file_manager.get_download_root = lambda: media_dir
        media.get_download_root = lambda: media_dir
        playlists_api.get_download_root = lambda: media_dir
        try:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://media.test"
            ) as client:
                uploaded = await post_local_file(
                    client,
                    "http://media.test/api/v1/materials/upload",
                    str(source),
                    data={"sub_path": ""},
                )
                assert uploaded["name"] == "本机故事.txt"
                assert (books / "本机故事.txt").read_text(encoding="utf-8") == "正文"

                playlists = (await client.get("http://media.test/api/v1/playlists")).json()
                default = next(item for item in playlists if item.get("is_default"))
                media_item = await post_local_file(
                    client,
                    f"http://media.test/api/v1/playlists/{default['id']}/upload",
                    str(video),
                )
                assert media_item["name"] == "本机片段.mp4"
                assert (media_dir / "本机片段.mp4").read_bytes() == b"\x00\x00clip"
                removed = await client.delete(
                    f"http://media.test/api/v1/playlists/{default['id']}/items/{media_item['id']}"
                )
                assert removed.status_code == 200, removed.text
        finally:
            material_service.get_materials_root = original_materials
            file_manager.get_download_root = original_download
            media.get_download_root = original_download
            playlists_api.get_download_root = original_playlist_download

        print("OK: mcp local upload")
        return 0
    finally:
        shutil.rmtree(library, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
