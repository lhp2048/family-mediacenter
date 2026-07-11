#!/usr/bin/env python3
"""Normalize shell scripts to Unix LF line endings."""

from __future__ import annotations

import sys
from pathlib import Path


def normalize_file(path: Path) -> bool:
    raw = path.read_bytes()
    if b"\r" not in raw:
        return False
    path.write_bytes(raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
    return True


def collect_paths(raw_paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in raw_paths:
        path = Path(raw)
        if path.is_dir():
            files.extend(sorted(path.rglob("*.sh")))
        elif path.is_file() and path.suffix == ".sh":
            files.append(path)
    return files


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: normalize_shell.py <file-or-dir> ...", file=sys.stderr)
        return 1

    changed = 0
    for path in collect_paths(args):
        if normalize_file(path):
            print(f"normalized: {path}")
            changed += 1
    if changed:
        print(f"done: {changed} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
