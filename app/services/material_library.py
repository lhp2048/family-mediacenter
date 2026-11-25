"""Manage files inside the ebook library. Paths cannot leave the library root."""

import shutil
from pathlib import Path
from urllib.parse import unquote, urlparse

from fastapi import UploadFile

from app.models.task import TaskCreate, TaskResponse
from app.services import material_service
from app.services.material_service import _normalize_materials_subpath
from app.services.local_upload import write_new_file
from app.services.material_share import material_share_service
from app.services.task_manager import task_manager
from app.utils.materials import EBOOK_EXT
from app.utils.url_extract import extract_url_from_text


def _root() -> Path:
    return material_service.get_materials_root().resolve()


def _lexical(sub_path: str) -> tuple[str, Path]:
    """Path under the library root. The final component is not resolved, so symlinks stay links."""
    rel = _normalize_materials_subpath(sub_path)
    root = _root()
    target = root.joinpath(*rel.split("/")) if rel else root
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("非法路径") from exc
    return rel, target


def _reject_symlinks(target: Path, root: Path, *, allow_final: bool = False) -> None:
    current = target
    while True:
        if current.is_symlink() and not (allow_final and current == target):
            raise ValueError("不能操作符号链接")
        if current == root:
            return
        parent = current.parent
        if parent == current:
            raise ValueError("非法路径")
        current = parent


def _require(sub_path: str, *, allow_symlink: bool = False) -> tuple[str, Path]:
    rel, target = _lexical(sub_path)
    _reject_symlinks(target, _root(), allow_final=allow_symlink)
    if target.is_symlink():
        return rel, target
    if not target.exists():
        raise ValueError("路径不存在")
    return rel, target


def subpath_in_library(file_path: str) -> str | None:
    if not file_path:
        return None
    path = Path(file_path)
    if path.is_symlink():
        return None
    root = _root()
    try:
        rel = path.resolve().relative_to(root)
    except (OSError, ValueError):
        return None
    if not rel.parts:
        return None
    return rel.as_posix()


def _single_name(name: str) -> str:
    cleaned = (name or "").strip().replace("\\", "/")
    if (
        not cleaned
        or "/" in cleaned
        or cleaned in {".", ".."}
        or cleaned.startswith(".")
    ):
        raise ValueError("非法名称")
    return cleaned


def _ebook_name(name: str) -> str:
    cleaned = _single_name(name)
    if Path(cleaned).suffix.lower() not in EBOOK_EXT:
        raise ValueError("只支持 pdf、epub、txt、md")
    return cleaned


def _entry(path: Path, rel: str) -> dict:
    return {"path": rel, "name": path.name, "is_dir": path.is_dir()}


def create_folder(path: str) -> dict:
    rel, target = _lexical(path)
    if not rel:
        raise ValueError("目录名不能为空")
    root = _root()
    if target.is_symlink():
        raise ValueError("不能操作符号链接")
    if target.exists() and not target.is_dir():
        raise ValueError("同名文件已存在")
    current = target.parent
    while current != root:
        if current.is_symlink():
            raise ValueError("不能操作符号链接")
        if current.exists() and not current.is_dir():
            raise ValueError("同名文件已存在")
        current = current.parent
    try:
        target.mkdir(parents=True, exist_ok=True)
    except FileExistsError as exc:
        raise ValueError("同名文件已存在") from exc
    return _entry(target, rel)


async def _move_path(src: Path, dest: Path, old_rel: str, new_rel: str) -> None:
    snapshots = await material_share_service.relocate(old_rel, new_rel)
    try:
        shutil.move(str(src), str(dest))
    except Exception:
        await material_share_service.restore_shares(snapshots)
        raise


async def rename_entry(path: str, name: str) -> dict:
    rel, target = _require(path)
    if not rel:
        raise ValueError("不能重命名书库根目录")
    if target.is_file():
        new_name = _ebook_name(name)
    elif target.is_dir():
        new_name = _single_name(name)
    else:
        raise ValueError("路径不存在")
    dest = target.parent / new_name
    if dest.is_symlink():
        raise ValueError("不能操作符号链接")
    if dest.exists():
        raise ValueError("同名文件已存在")
    new_rel = Path(rel).with_name(new_name).as_posix()
    await _move_path(target, dest, rel, new_rel)
    return _entry(dest, new_rel)


async def move_entry(path: str, dest: str) -> dict:
    rel, target = _require(path)
    if not rel:
        raise ValueError("不能移动书库根目录")
    dest_rel, dest_dir = _require(dest)
    if not dest_dir.is_dir():
        raise ValueError("目标不是目录")
    if dest_rel == rel or dest_rel.startswith(rel + "/"):
        raise ValueError("不能移动到自身或子目录")
    new_path = dest_dir / target.name
    if new_path.is_symlink():
        raise ValueError("不能操作符号链接")
    if new_path.exists():
        raise ValueError("同名文件已存在")
    new_rel = f"{dest_rel}/{target.name}".strip("/")
    await _move_path(target, new_path, rel, new_rel)
    return _entry(new_path, new_rel)


async def delete_entry(path: str) -> dict:
    rel, target = _require(path, allow_symlink=True)
    if not rel:
        raise ValueError("不能删除书库根目录")
    snapshots = await material_share_service.disable_under(rel)
    try:
        if target.is_symlink() or target.is_file():
            target.unlink()
        elif target.is_dir():
            shutil.rmtree(target)
        else:
            raise ValueError("路径不存在")
    except Exception:
        await material_share_service.restore_shares(snapshots)
        raise
    return {"ok": True, "path": rel}


async def upload_ebook(sub_path: str, filename: str, upload: UploadFile) -> dict:
    folder_rel, folder = _require(sub_path)
    if not folder.is_dir():
        raise ValueError("目标不是目录")
    name = _ebook_name(Path(filename or "").name)
    dest = folder / name
    if dest.is_symlink() or dest.exists():
        raise ValueError("同名文件已存在")
    await write_new_file(dest, upload)
    rel = f"{folder_rel}/{name}".strip("/")
    return _entry(dest, rel)


def _filename_from_url(url: str) -> str:
    return Path(unquote(urlparse(url).path)).name


async def import_ebook(url: str, sub_path: str = "", filename: str = "") -> TaskResponse:
    raw = extract_url_from_text(url).strip()
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("只支持 http 或 https 直链")
    _folder_rel, folder = _require(sub_path)
    if not folder.is_dir():
        raise ValueError("目标不是目录")
    chosen = (filename or "").strip() or _filename_from_url(raw)
    if not chosen or chosen in {".", ".."} or "/" in chosen or "\\" in chosen:
        raise ValueError("无法从链接判断文件名，请提供 filename")
    name = _ebook_name(chosen)
    candidate = folder / name
    if candidate.is_symlink() or candidate.exists():
        raise ValueError("同名文件已存在")
    if await task_manager.download_name_reserved(str(folder), name):
        raise ValueError("同名文件已存在")
    return await task_manager.create_task(
        TaskCreate(
            url=raw,
            engine="aria2",
            output_dir=str(folder),
            options={"filename": name},
        ),
        preserve_filename=True,
    )
