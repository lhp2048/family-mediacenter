#!/usr/bin/env python3
"""从 skills/*/SKILL.md 同步 family-product.json 的 skills 描述（打包前调用）。"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
MANIFEST_PATH = ROOT / "family-product.json"

DEFAULT_INSTALL_SCRIPTS = {
    "workbuddy": {
        "unix": "scripts/install-workbuddy-skill.sh",
        "windows": "scripts/install-workbuddy-skill.bat",
        "args": [],
    },
    "cursor": {
        "unix": "scripts/install-skill.sh",
        "windows": "scripts/install-skill.bat",
        "args": ["--user"],
    },
}


def parse_skill_frontmatter(skill_md: Path) -> dict[str, str]:
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    block = text[3:end]
    data: dict[str, str] = {}
    for line in block.splitlines():
        match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line.strip())
        if match:
            data[match.group(1)] = match.group(2).strip()
    return data


def discover_skills() -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    if not SKILLS_DIR.is_dir():
        return items
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue
        meta = parse_skill_frontmatter(skill_md)
        skill_id = meta.get("name") or skill_dir.name
        items.append(
            {
                "id": skill_id,
                "title": meta.get("name") or skill_dir.name,
                "description": meta.get("description") or "",
                "version": meta.get("version") or "",
                "path": f"skills/{skill_dir.name}",
            }
        )
    return items


def sync_manifest(*, manifest_path: Path | None = None, dist_path: Path | None = None) -> dict:
    manifest_path = manifest_path or MANIFEST_PATH
    if not manifest_path.is_file():
        raise FileNotFoundError(f"未找到 {manifest_path}")

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    items = discover_skills()
    existing = data.get("skills") if isinstance(data.get("skills"), dict) else {}
    install_scripts = existing.get("installScripts")
    if not isinstance(install_scripts, dict) or not install_scripts:
        install_scripts = DEFAULT_INSTALL_SCRIPTS

    skills_block = {
        "installScripts": install_scripts,
        "items": items,
    }
    data["skills"] = skills_block
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    manifest_path.write_text(text, encoding="utf-8")

    if dist_path is not None:
        dist_manifest = dist_path / "family-product.json"
        if dist_manifest.is_file():
            dist_manifest.write_text(text, encoding="utf-8")

    return skills_block


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Sync skills metadata into family-product.json")
    parser.add_argument(
        "--manifest",
        default=str(MANIFEST_PATH),
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
        skills = sync_manifest(manifest_path=manifest_path, dist_path=dist_path)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    count = len(skills.get("items") or [])
    print(f"skills synced: {count} item(s)")
    for item in skills.get("items") or []:
        version = item.get("version") or "?"
        print(f"  - {item.get('id')} v{version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
