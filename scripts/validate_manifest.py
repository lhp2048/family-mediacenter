#!/usr/bin/env python3
"""校验 family-product.json，打包前调用。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REQUIRED_FIELDS = ("manifestVersion", "id", "title")


def validate_file(manifest_path: Path, *, check_dist: Path | None = None) -> dict:
    if not manifest_path.is_file():
        raise FileNotFoundError(f"未找到 {manifest_path}")
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    for key in REQUIRED_FIELDS:
        if not data.get(key):
            raise ValueError(f"family-product.json 缺少必填字段: {key}")
    if data.get("manifestVersion") != 1:
        raise ValueError("manifestVersion 必须为 1")
    if check_dist and check_dist.is_dir():
        missing = [
            name for name in data.get("validateFiles", []) if not (check_dist / name).is_file()
        ]
        if missing:
            raise FileNotFoundError(f"dist 缺少 validateFiles: {', '.join(missing)}")
    return data


def main() -> int:
    import argparse

    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Validate family-product.json")
    parser.add_argument("manifest", nargs="?", default=str(root / "family-product.json"))
    parser.add_argument("--dist", default="")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    dist = Path(args.dist).resolve() if args.dist else None
    try:
        manifest = validate_file(manifest_path, check_dist=dist)
    except (ValueError, FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("OK: family-product.json")
    print(f"  id:      {manifest['id']}")
    print(f"  title:   {manifest['title']}")
    print(f"  version: {manifest.get('version') or '(未填)'}")
    print(f"  port:    {manifest.get('port') or '(无)'}")
    if manifest.get("zipNameHint"):
        print(f"  zip:     {manifest['zipNameHint']}")
    skills = manifest.get("skills")
    if isinstance(skills, dict) and skills.get("items"):
        print(f"  skills:  {len(skills['items'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
