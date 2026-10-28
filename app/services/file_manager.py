import asyncio
import os
import shutil
import stat as stat_mode
from datetime import datetime
from math import ceil
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from app.config import PROJECT_ROOT, load_settings, resolve_download_dir
from app.models.pagination import normalize_page


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


class FileStat(BaseModel):
    path: str
    exists: bool = False
    is_dir: bool = False
    size: int = 0
    modified_at: Optional[datetime] = None


FILE_INFO_LIMIT = 500


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


def download_storage_prefix() -> str:
    """downloads/multimedia relative to downloads/, or empty if they are the same."""
    storage = get_storage_root().resolve()
    download = get_download_root().resolve()
    try:
        rel = download.relative_to(storage).as_posix()
    except ValueError:
        return ""
    if rel in ("", "."):
        return ""
    return rel


def to_storage_rel(download_rel: str) -> str:
    """Map a path under downloads/multimedia onto the /files/ storage root."""
    rel = _normalize_rel_path(download_rel)
    prefix = download_storage_prefix()
    if not prefix:
        return rel
    if rel == prefix or rel.startswith(prefix + "/"):
        return rel
    return f"{prefix}/{rel}" if rel else prefix


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

    try:
        with os.scandir(current) as iterator:
            children = [entry for entry in iterator if not entry.name.startswith(".")]
    except OSError as e:
        raise ValueError(str(e)) from e

    # Name and directory bit come from the directory listing. Size and mtime
    # are filled later by stat_download_paths for the rows on screen.
    children.sort(key=lambda entry: (not entry.is_dir(), entry.name.lower()))

    parent = ""
    if rel:
        parent = str(Path(rel).parent).replace("\\", "/")
        if parent == ".":
            parent = ""

    total = len(children)
    pg = page
    ps = page_size
    if pg is not None:
        pg = normalize_page(pg)
        # Files list allows up to 500 when searching / bulk ops
        ps = max(1, min(int(ps or 15), 500))
        start = (pg - 1) * ps
        page_children = children[start : start + ps]
        total_pages = ceil(total / ps) if total > 0 else 0
        if total > 0 and total_pages == 0:
            total_pages = 1
    else:
        pg = 1
        ps = total if total > 0 else 15
        total_pages = 1 if total > 0 else 0
        page_children = children

    entries = [_entry_from_scandir(child, root, public_base) for child in page_children]

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


def _entry_from_scandir(child: os.DirEntry, root: Path, public_base: str) -> FileEntry:
    rel_child = Path(child.path).relative_to(root).as_posix()
    is_dir = child.is_dir()
    return FileEntry(
        name=child.name,
        path=rel_child,
        is_dir=is_dir,
        public_url=build_public_url(to_storage_rel(rel_child), public_base) if not is_dir else "",
    )


def stat_download_paths(rel_paths: list[str]) -> list[FileStat]:
    """Stat only the requested download-relative paths."""
    unique: list[str] = []
    seen: set[str] = set()
    for raw in rel_paths:
        if len(unique) >= FILE_INFO_LIMIT:
            break
        try:
            rel = _normalize_rel_path(raw)
        except ValueError:
            continue
        if not rel or rel in seen:
            continue
        seen.add(rel)
        unique.append(rel)

    items: list[FileStat] = []
    for rel in unique:
        try:
            target = resolve_safe_path(rel)
            st = target.stat()
        except (OSError, ValueError):
            items.append(FileStat(path=rel, exists=False))
            continue
        is_dir = stat_mode.S_ISDIR(st.st_mode)
        items.append(
            FileStat(
                path=rel,
                exists=True,
                is_dir=is_dir,
                size=0 if is_dir else st.st_size,
                modified_at=datetime.fromtimestamp(st.st_mtime),
            )
        )
    return items


async def list_directory_async(
    rel_path: str,
    public_base: str,
    page: Optional[int] = None,
    page_size: Optional[int] = None,
) -> FileListResponse:
    return await asyncio.to_thread(list_directory, rel_path, public_base, page, page_size)


async def stat_download_paths_async(rel_paths: list[str]) -> list[FileStat]:
    return await asyncio.to_thread(stat_download_paths, rel_paths)


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


class FileRenameReplaceItem(BaseModel):
    old_rel_path: str
    new_rel_path: str
    old_name: str
    new_name: str
    refs_updated: int = 0


class FileRenameReplaceResult(BaseModel):
    ok: bool = True
    dry_run: bool = False
    find: str = ""
    replace: str = ""
    scope: str = "dir"
    path: str = ""
    renamed: list[FileRenameReplaceItem] = []
    skipped: list[str] = []
    errors: list[str] = []
    message: str = ""


def _sanitize_filename(name: str) -> str:
    bad = '<>:"/\\|?*'
    out = "".join("_" if ch in bad else ch for ch in name)
    return out.strip(" .")


def _iter_files_for_rename(scope: str, base_path: str) -> list[tuple[Path, str]]:
    """Return (abs_path, download_rel) for files in scope. scope: dir | all."""
    root = get_download_root().resolve()
    base = resolve_safe_path(base_path)
    if not base.exists() or not base.is_dir():
        raise ValueError("目录不存在")

    scope_norm = (scope or "dir").strip().lower()
    if scope_norm not in ("dir", "all"):
        raise ValueError("scope 须为 dir 或 all")

    out: list[tuple[Path, str]] = []
    if scope_norm == "dir":
        try:
            children = sorted(base.iterdir(), key=lambda p: p.name.lower())
        except OSError as e:
            raise ValueError(str(e)) from e
        for child in children:
            if child.name.startswith(".") or not child.is_file():
                continue
            out.append((child, child.relative_to(root).as_posix()))
        return out

    # all: entire download root tree
    try:
        for child in sorted(root.rglob("*"), key=lambda p: p.as_posix().lower()):
            if not child.is_file() or child.name.startswith("."):
                continue
            if any(part.startswith(".") for part in child.relative_to(root).parts):
                continue
            out.append((child, child.relative_to(root).as_posix()))
    except OSError as e:
        raise ValueError(str(e)) from e
    return out


def rename_replace_files(
    find: str,
    replace: str = "",
    *,
    scope: str = "dir",
    base_path: str = "",
    dry_run: bool = False,
) -> FileRenameReplaceResult:
    """Find/replace in basenames under download root. scope=dir (current) or all."""
    find = find or ""
    if not find:
        raise ValueError("查找字符串不能为空")
    replace = replace if replace is not None else ""
    rel_base = _normalize_rel_path(base_path)
    scope_norm = (scope or "dir").strip().lower()
    if scope_norm not in ("dir", "all"):
        raise ValueError("scope 须为 dir 或 all")

    result = FileRenameReplaceResult(
        ok=True,
        dry_run=dry_run,
        find=find,
        replace=replace,
        scope=scope_norm,
        path=rel_base,
    )

    files = _iter_files_for_rename(scope_norm, rel_base)
    plans: list[tuple[Path, Path, str, str, str, str]] = []
    # src, dst, old_rel, new_rel, old_name, new_name
    planned_dst: set[str] = set()

    for src, old_rel in files:
        old_name = src.name
        if find not in old_name:
            continue
        new_name = _sanitize_filename(old_name.replace(find, replace))
        if not new_name:
            result.errors.append(f"替换后文件名为空: {old_name}")
            continue
        if new_name == old_name:
            result.skipped.append(f"无变化: {old_name}")
            continue
        parent = Path(old_rel).parent
        new_rel = (
            new_name if str(parent) in (".", "") else f"{parent.as_posix()}/{new_name}"
        )
        try:
            dst = resolve_safe_path(new_rel)
        except ValueError as e:
            result.errors.append(f"{old_name}: {e}")
            continue
        if new_rel in planned_dst:
            result.errors.append(f"目标冲突: {new_rel}")
            continue
        if dst.exists() and src.resolve() != dst.resolve():
            result.errors.append(f"目标已存在: {new_rel}")
            continue
        planned_dst.add(new_rel)
        plans.append((src, dst, old_rel, new_rel, old_name, new_name))

    for src, dst, old_rel, new_rel, old_name, new_name in plans:
        if dry_run:
            result.renamed.append(
                FileRenameReplaceItem(
                    old_rel_path=old_rel,
                    new_rel_path=new_rel,
                    old_name=old_name,
                    new_name=new_name,
                )
            )
            continue
        try:
            src.rename(dst)
        except OSError as e:
            result.errors.append(f"重命名失败 {old_name} → {new_name}: {e}")
            continue
        result.renamed.append(
            FileRenameReplaceItem(
                old_rel_path=old_rel,
                new_rel_path=new_rel,
                old_name=old_name,
                new_name=new_name,
            )
        )

    n = len(result.renamed)
    err_n = len(result.errors)
    if dry_run:
        result.message = f"预览：将重命名 {n} 个文件"
    elif n and not err_n:
        result.message = f"已重命名 {n} 个文件"
    elif n and err_n:
        result.message = f"已重命名 {n} 个，另有 {err_n} 个失败"
        result.ok = False
    elif err_n:
        result.message = f"重命名失败（{err_n}）"
        result.ok = False
    else:
        result.message = "没有需要重命名的文件"
    return result


def get_file_for_serve(rel_path: str) -> Path:
    rel = _normalize_rel_path(rel_path)
    if not rel:
        raise ValueError("无效文件路径")
    target = resolve_storage_safe_path(rel)
    if target.is_file():
        return target
    # Older links omit the multimedia/ prefix and point at the filename only.
    prefixed = to_storage_rel(rel)
    if prefixed != rel:
        alt = resolve_storage_safe_path(prefixed)
        if alt.is_file():
            return alt
    raise ValueError("文件不存在")
