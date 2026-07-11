import json
from datetime import datetime
from math import ceil
from pathlib import Path
from typing import Optional

from app.config import load_settings
from app.models.material import MaterialBrowseEntry, MaterialBrowseResponse, MaterialFolderMeta
from app.models.pagination import normalize_page, normalize_page_size
from app.services.file_manager import (
    build_public_url,
    get_storage_root,
    resolve_storage_safe_path,
)
from app.utils.materials import is_ebook_path, material_kind_for_path


def resolve_materials_dir(path: str | None = None) -> str:
    s = load_settings()
    storage_root = get_storage_root()
    rel = (path or s.materials.dir or "ebooks").strip().strip("/\\")
    if not rel:
        rel = "ebooks"
    target = Path(rel)
    if target.is_absolute():
        target = target.resolve()
        if target != storage_root and storage_root not in target.parents:
            raise ValueError("电子书目录必须在 downloads/ 目录内")
    else:
        target = (storage_root / rel).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return str(target)


def get_materials_root() -> Path:
    return Path(resolve_materials_dir())


def materials_rel_prefix() -> str:
    root = get_storage_root()
    materials_root = get_materials_root()
    try:
        return materials_root.relative_to(root).as_posix()
    except ValueError:
        return ""


def _read_meta(folder: Path) -> dict:
    meta_path = folder / "meta.json"
    if not meta_path.is_file():
        return {}
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def resolve_material_path(rel_path: str) -> Path:
    rel_prefix = materials_rel_prefix()
    rel = rel_path.replace("\\", "/").strip().strip("/")
    if rel_prefix and not rel.startswith(rel_prefix):
        rel = f"{rel_prefix}/{rel}".strip("/")
    return resolve_storage_safe_path(rel)


COVER_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def _normalize_materials_subpath(path: str) -> str:
    cleaned = path.replace("\\", "/").strip().strip("/")
    parts = [p for p in cleaned.split("/") if p and p not in (".", "..")]
    return "/".join(parts)


def resolve_materials_folder(sub_path: str) -> Path:
    materials_root = get_materials_root()
    rel = _normalize_materials_subpath(sub_path)
    target = (materials_root / rel).resolve() if rel else materials_root.resolve()
    root_resolved = materials_root.resolve()
    if target != root_resolved and root_resolved not in target.parents:
        raise ValueError("非法路径")
    if not target.is_dir():
        raise ValueError("目录不存在")
    return target


def _resolve_path_in_folder(folder: Path, name: str) -> Path | None:
    cleaned = name.strip().replace("\\", "/").strip("/")
    if not cleaned:
        return None
    candidate = (folder / cleaned).resolve()
    folder_resolved = folder.resolve()
    if candidate != folder_resolved and folder_resolved not in candidate.parents:
        return None
    if candidate.is_file():
        return candidate
    return None


def _public_rel(rel_prefix: str, sub_path: str, inner: str = "") -> str:
    parts = [p for p in (rel_prefix, sub_path, inner) if p]
    return "/".join(parts)


def _build_folder_meta(
    folder: Path,
    sub_path: str,
    rel_prefix: str,
    public_base: str,
) -> MaterialFolderMeta:
    meta = _read_meta(folder)
    folder_name = folder.name if sub_path else "书库"
    title = str(meta.get("title") or folder_name).strip() or folder_name
    description = str(meta.get("description") or meta.get("summary") or "").strip()
    author = str(meta.get("author") or "").strip()
    tags_raw = meta.get("tags") or []
    tags = (
        [str(t).strip() for t in tags_raw if str(t).strip()]
        if isinstance(tags_raw, list)
        else []
    )
    cover_url = ""
    cover_name = str(meta.get("cover") or "").strip()
    if cover_name:
        cover_path = _resolve_path_in_folder(folder, cover_name)
        if cover_path and cover_path.suffix.lower() in COVER_SUFFIXES:
            inner = cover_path.relative_to(folder).as_posix()
            cover_rel = _public_rel(rel_prefix, sub_path, inner)
            cover_url = build_public_url(cover_rel, public_base)
    return MaterialFolderMeta(
        title=title,
        description=description,
        author=author,
        tags=tags,
        cover_url=cover_url,
    )


def _browse_entry_sort_key(entry: MaterialBrowseEntry) -> tuple[int, str]:
    return (0 if entry.is_dir else 1, entry.name.lower())


def browse_materials(
    public_base: str,
    sub_path: str = "",
    page: Optional[int] = None,
    page_size: Optional[int] = None,
) -> MaterialBrowseResponse:
    materials_root = get_materials_root()
    rel_prefix = materials_rel_prefix()
    configured_dir = load_settings().materials.dir or "ebooks"

    if not materials_root.exists():
        raise ValueError("电子书目录不存在")

    rel_path = _normalize_materials_subpath(sub_path)
    folder = resolve_materials_folder(rel_path)
    parent = ""
    if rel_path:
        parent_parts = rel_path.split("/")[:-1]
        parent = "/".join(parent_parts)

    folder_meta = _build_folder_meta(folder, rel_path, rel_prefix, public_base)

    entries: list[MaterialBrowseEntry] = []
    try:
        children = sorted(folder.iterdir(), key=lambda p: (0 if p.is_dir() else 1, p.name.lower()))
    except OSError as e:
        raise ValueError(str(e)) from e

    for child in children:
        if child.name.startswith(".") or child.name == "meta.json":
            continue
        child_sub = f"{rel_path}/{child.name}".strip("/") if rel_path else child.name
        child_rel = _public_rel(rel_prefix, child_sub)
        try:
            stat = child.stat()
            modified_at = datetime.fromtimestamp(stat.st_mtime)
            size = stat.st_size
        except OSError:
            modified_at = None
            size = 0

        if child.is_dir():
            entries.append(
                MaterialBrowseEntry(
                    name=child.name,
                    sub_path=child_sub,
                    rel_path=child_rel,
                    is_dir=True,
                    modified_at=modified_at,
                )
            )
            continue

        if not is_ebook_path(child):
            continue

        entries.append(
            MaterialBrowseEntry(
                name=child.name,
                sub_path=child_sub,
                rel_path=child_rel,
                is_dir=False,
                kind=material_kind_for_path(child),
                size=size,
                modified_at=modified_at,
                public_url=build_public_url(child_rel, public_base),
            )
        )

    entries.sort(key=_browse_entry_sort_key)

    total = len(entries)
    pg = page
    ps = page_size
    if pg is not None:
        pg = normalize_page(pg)
        ps = normalize_page_size(ps or 15)
        start = (pg - 1) * ps
        entries = entries[start : start + ps]
        total_pages = ceil(total / ps) if total > 0 else 0
        if total > 0 and total_pages == 0:
            total_pages = 1
    else:
        pg = 1
        ps = total if total > 0 else 15
        total_pages = 1 if total > 0 else 0

    return MaterialBrowseResponse(
        root=str(materials_root),
        dir=configured_dir,
        path=rel_path,
        parent=parent,
        folder=folder_meta,
        entries=entries,
        total=total,
        page=pg,
        page_size=ps,
        total_pages=total_pages,
    )


def resolve_material_file(public_base: str, sub_path: str) -> dict[str, str]:
    """Resolve a material file by sub_path (relative to materials root) for embed reader."""
    rel = _normalize_materials_subpath(sub_path)
    if not rel:
        raise ValueError("path 不能为空")
    materials_root = get_materials_root().resolve()
    file_path = (materials_root / rel).resolve()
    if file_path != materials_root and materials_root not in file_path.parents:
        raise ValueError("非法路径")
    if not file_path.is_file():
        raise ValueError("文件不存在")
    if not is_ebook_path(file_path):
        raise ValueError("不支持的电子书格式")
    rel_prefix = materials_rel_prefix()
    public_rel = _public_rel(rel_prefix, rel)
    return {
        "name": file_path.name,
        "sub_path": rel,
        "kind": material_kind_for_path(file_path),
        "public_url": build_public_url(public_rel, public_base),
    }
