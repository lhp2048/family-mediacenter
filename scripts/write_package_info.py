#!/usr/bin/env python3
"""打包完成后写入 dist_out/*.package.json 便于门户集成。"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_manifest(manifest_path: Path, dist: Path | None) -> dict:
    if not manifest_path.is_file():
        raise FileNotFoundError(f"未找到 {manifest_path}")
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if dist and dist.is_dir():
        missing = [
            name for name in data.get("validateFiles", []) if not (dist / name).is_file()
        ]
        if missing:
            raise FileNotFoundError(f"dist 缺少文件: {', '.join(missing)}")
    return data


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Write package sidecar metadata")
    parser.add_argument("--manifest", default=str(ROOT / "family-product.json"))
    parser.add_argument("--zip", required=True)
    parser.add_argument("--dist", default=str(ROOT / "dist"))
    parser.add_argument("--out-dir", default=str(ROOT / "dist_out"))
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    zip_path = Path(args.zip).resolve()
    dist = Path(args.dist).resolve() if args.dist else None
    out_dir = Path(args.out_dir).resolve()

    try:
        manifest = _load_manifest(manifest_path, dist)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "productId": manifest["id"],
        "title": manifest["title"],
        "version": manifest.get("version") or "",
        "port": manifest.get("port"),
        "zipFile": zip_path.name,
        "zipPath": str(zip_path),
        "zipBytes": zip_path.stat().st_size if zip_path.is_file() else 0,
        "builtAt": datetime.now(timezone.utc).isoformat(),
        "monorepoPath": manifest.get("monorepoPath") or "",
        "packageType": manifest.get("packageType") or "",
        "defaultInstallDir": manifest.get("defaultInstallDir") or "",
        "manifestFile": "family-product.json",
        "portalInstall": "http://127.0.0.1:18024/deploy.html",
    }
    sidecar = out_dir / f"{manifest['id']}.package.json"
    sidecar.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    index_path = out_dir / "package-index.json"
    index: dict = {"updatedAt": payload["builtAt"], "packages": []}
    if index_path.is_file():
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    packages = [item for item in index.get("packages", []) if item.get("productId") != manifest["id"]]
    packages.append(payload)
    index["packages"] = sorted(packages, key=lambda item: item.get("productId") or "")
    index["updatedAt"] = payload["builtAt"]
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote: {sidecar}")
    print(f"Index: {index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
