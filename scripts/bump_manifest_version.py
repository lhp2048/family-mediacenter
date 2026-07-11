#!/usr/bin/env python3
"""打包前将 family-product.json 的 version 更新为 yy.Mdd.hhmm（见仓库 REQ.txt）。"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def format_portal_version(when: datetime | None = None) -> str:
    """格式: yy.Mdd.hhmm，例如 2026-06-27 15:47 -> 26.627.1547"""
    when = when or datetime.now()
    yy = when.year % 100
    mdd = f"{when.month}{when.day:02d}"
    hhmm = f"{when.hour:02d}{when.minute:02d}"
    return f"{yy}.{mdd}.{hhmm}"


def bump_manifest_version(
    manifest_path: Path,
    *,
    dist_path: Path | None = None,
    when: datetime | None = None,
) -> str:
    if not manifest_path.is_file():
        raise FileNotFoundError(f"未找到 {manifest_path}")

    version = format_portal_version(when)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["version"] = version
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    manifest_path.write_text(text, encoding="utf-8")

    if dist_path is not None:
        dist_manifest = dist_path / "family-product.json"
        if dist_manifest.is_file():
            dist_manifest.write_text(text, encoding="utf-8")

    return version


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Bump family-product.json version at pack time")
    parser.add_argument(
        "--manifest",
        default=str(ROOT / "family-product.json"),
        help="Path to family-product.json",
    )
    parser.add_argument(
        "--dist",
        default=str(ROOT / "dist"),
        help="Sync dist/family-product.json if present",
    )
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    dist_path = Path(args.dist).resolve() if args.dist else None

    try:
        version = bump_manifest_version(manifest_path, dist_path=dist_path)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"version -> {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
