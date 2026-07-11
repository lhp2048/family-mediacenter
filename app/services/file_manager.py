import os
import shutil
from datetime import datetime
from math import ceil
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from app.config import PROJECT_ROOT, load_settings, resolve_download_dir
from app.models.pagination import normalize_page, normalize_page_size


class FileEntry(BaseModel):
    name: str
    path: str
    is_dir: bool
    size: int = 0
    modified_at: Optional[datetime] = None
    public_url: str = ""


class FileListResponse(BaseModel):
    root: str
    path: str
    parent: str
    entries: list[FileEntry]
    total: int = 0
    page: int = 1
    page_size: int = 15
    total_pages: int = 0


def get_download_root() -> Path:
    s = load_settings()
    return Path(resolve_download_dir(s.download.default_dir))


def get_storage_root() -> Path:
    """Whole downloads/ tree (multimedia + ebooks, etc.)."""
    root = (PROJECT_ROOT / "downloads").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _normalize_rel_path(path: str) -> str:
    cleaned = path.replace("\\", "/").strip().strip("/")
    if cleaned in (".", ""):
        return ""
    parts = [p for p in cleaned.split("/") if p and p != "."]
    if any(p == ".." for p in parts):
        raise ValueError("非法路径")
    return "/".join(parts)


def normalize_rel_path(path: str) -> str:
    return _normalize_rel_path(path)


def resolve_safe_path(rel_path: str) -> Path:
    root = get_download_root()
    rel = _normalize_rel_path(rel_path)
    target = (root / rel).resolve()
    root_resolved = root.resolve()
    if target != root_resolved and root_resolved not in target.parents:
        raise ValueError("路径超出下载目录")
    return target


def resolve_storage_safe_path(rel_path: str) -> Path:
    root = get_storage_root()
    rel = _normalize_rel_path(rel_path)
    target = (root / rel).resolve()
    root_resolved = root.resolve()
    if target != root_resolved and root_resolved not in target.parents:
        raise ValueError("路径超出存储目录")
    return target


def build_public_url(rel_path: str, base_url: str) -> str:
    rel = _normalize_rel_path(rel_path)
    if not rel:
        return ""
    encoded = "/".join(_encode_path_part(p) for p in rel.split("/"))
    return f"{base_url.rstrip('/')}/files/{encoded}"


def _encode_path_part(part: str) -> str:
    from urllib.parse import quote

    return quote(part, safe="")


def get_public_base_url(request_base: str) -> str:
    s = load_settings()
    if s.files.public_base_url:
        return s.files.public_base_url.rstrip("/")
    return request_base.rstrip("/")


def list_directory(
    rel_path: str,
    public_base: str,
    page: Optional[int] = None,
    page_size: Optional[int] = None,
) -> FileListResponse:
    root = get_download_root()
    rel = _normalize_rel_path(rel_path)
    current = resolve_safe_path(rel)
    if not current.exists():
        raise ValueError("目录不存在")
    if not current.is_dir():
        raise ValueError("不是目录")

    entries: list[FileEntry] = []
    try:
        children = sorted(
            current.iterdir(),
            key=lambda p: (not p.is_dir(), p.name.lower()),
        )
    except OSError as e:
        raise ValueError(str(e)) from e

    for child in children:
        if child.name.startswith("."):
            continue
        rel_child = child.relative_to(root).as_posix()
        stat = child.stat()
        entry = FileEntry(
            name=child.name,
            path=rel_child,
            is_dir=child.is_dir(),
            size=stat.st_size if child.is_file() else 0,
            modified_at=datetime.fromtimestamp(stat.st_mtime),
            public_url=build_public_url(rel_child, public_base) if child.is_file() else "",
        )
        entries.append(entry)

    parent = ""
    if rel:
        parent = str(Path(rel).parent).replace("\\", "/")
        if parent == ".":
            parent = ""

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

    return FileListResponse(
        root=str(root),
        path=rel,
        parent=parent,
        entries=entries,
        total=total,
        page=pg,
        page_size=ps,
        total_pages=total_pages,
    )


def delete_path(rel_path: str) -> None:
    rel = _normalize_rel_path(rel_path)
    if not rel:
        raise ValueError("不能删除根目录")
    target = resolve_safe_path(rel)
    if not target.exists():
        raise ValueError("文件不存在")
    root = get_download_root().resolve()
    if target.resolve() == root:
        raise ValueError("不能删除根目录")
    if target.is_dir():
        shutil.rmtree(target)
    else:
        os.remove(target)


def get_file_for_serve(rel_path: str) -> Path:
    rel = _normalize_rel_path(rel_path)
    if not rel:
        raise ValueError("无效文件路径")
    target = resolve_storage_safe_path(rel)
    if not target.exists() or not target.is_file():
        raise ValueError("文件不存在")
    return target
