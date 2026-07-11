#!/usr/bin/env python3
"""Create zip from dist/ using forward slashes."""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

SKIP_PARTS = {"__pycache__", ".pytest_cache", ".venv", "logs", "data", "downloads"}
SKIP_SUFFIXES = {".pyc", ".pyo"}


def should_skip(path: Path) -> bool:
    if any(part in SKIP_PARTS for part in path.parts):
        return True
    return path.suffix.lower() in SKIP_SUFFIXES


def pack_dist(dist_dir: Path, zip_path: Path) -> int:
    if not dist_dir.is_dir():
        print(f"ERROR: dist not found: {dist_dir}", file=sys.stderr)
        return 1

    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.is_file():
        zip_path.unlink()

    count = 0
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in sorted(dist_dir.rglob("*")):
            if not file_path.is_file() or should_skip(file_path):
                continue
            arcname = file_path.relative_to(dist_dir).as_posix()
            archive.write(file_path, arcname)
            count += 1

    print(f"Packed {count} files -> {zip_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Pack dist directory into zip")
    parser.add_argument("dist", type=Path)
    parser.add_argument("zip", type=Path)
    args = parser.parse_args()
    return pack_dist(args.dist.resolve(), args.zip.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
