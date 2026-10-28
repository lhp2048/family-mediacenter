#!/usr/bin/env python3
"""Smoke-test files rename-replace (dir vs all scope)."""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from app.config import load_settings, resolve_download_dir
    from app.services.file_manager import rename_replace_files

    s = load_settings()
    download = Path(resolve_download_dir(s.download.default_dir))
    download.mkdir(parents=True, exist_ok=True)

    tmp = Path(tempfile.mkdtemp(prefix="rename_smoke_", dir=download))
    sub = tmp / "nested"
    sub.mkdir()
    (tmp / "clip_[HD].mp4").write_bytes(b"a")
    (tmp / "other.txt").write_text("x", encoding="utf-8")
    (sub / "clip_[HD]_deep.mp4").write_bytes(b"b")

    rel_tmp = tmp.relative_to(download).as_posix()
    try:
        preview = rename_replace_files(
            "[HD]", "", scope="dir", base_path=rel_tmp, dry_run=True
        )
        names = {r.old_name for r in preview.renamed}
        assert "clip_[HD].mp4" in names, names
        assert "clip_[HD]_deep.mp4" not in names, "dir scope should not include nested"

        preview_all = rename_replace_files(
            "[HD]", "", scope="all", base_path=rel_tmp, dry_run=True
        )
        names_all = {r.old_name for r in preview_all.renamed}
        assert "clip_[HD].mp4" in names_all
        assert "clip_[HD]_deep.mp4" in names_all

        applied = rename_replace_files(
            "[HD]", "", scope="dir", base_path=rel_tmp, dry_run=False
        )
        assert applied.ok and len(applied.renamed) == 1
        assert (tmp / "clip_.mp4").is_file()
        assert not (tmp / "clip_[HD].mp4").exists()
        assert (sub / "clip_[HD]_deep.mp4").is_file()

        print("ok: files rename-replace dir/all scopes")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
