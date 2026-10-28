#!/usr/bin/env python3
"""Directory listing stays name-only; size and mtime are a separate stat."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models.playlist import PlaylistItemORM  # noqa: E402
from app.services.file_manager import (  # noqa: E402
    get_download_root,
    list_directory,
    stat_download_paths,
)
from app.services.playlist_service import _scan_media_names, playlist_service  # noqa: E402


def main() -> int:
    root = get_download_root()
    folder = root / "_list_probe"
    folder.mkdir(parents=True, exist_ok=True)
    sample = folder / "clip.mp4"
    sample.write_bytes(b"12345")
    try:
        listing = list_directory("_list_probe", "http://127.0.0.1:18026", page=1, page_size=15)
        entry = next(item for item in listing.entries if item.name == "clip.mp4")
        assert entry.modified_at is None, entry
        assert entry.size == 0
        assert entry.public_url.endswith("clip.mp4")

        stats = {row.path: row for row in stat_download_paths([
            "_list_probe/clip.mp4",
            "_list_probe/missing.mp4",
        ])}
        assert stats["_list_probe/clip.mp4"].exists
        assert stats["_list_probe/clip.mp4"].size == 5
        assert stats["_list_probe/clip.mp4"].modified_at is not None
        assert stats["_list_probe/missing.mp4"].exists is False

        names = _scan_media_names(folder, False)
        assert ("clip.mp4", 0) in [(name, size) for _rel, name, size in names]

        item = PlaylistItemORM(
            id=1,
            playlist_id=1,
            rel_path="_list_probe/clip.mp4",
            title="clip",
            sort_order=0,
        )
        cold = playlist_service._item_to_response(item, "http://127.0.0.1:18026", probe=False)
        assert cold.info_ready is False
        assert cold.size == 0
        assert cold.public_url
        hot = playlist_service._item_to_response(item, "http://127.0.0.1:18026", probe=True)
        assert hot.info_ready is True
        assert hot.exists is True
        assert hot.size == 5
    finally:
        sample.unlink(missing_ok=True)
        folder.rmdir()
    print("OK: lazy file info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
