import secrets
from pathlib import Path
from urllib.parse import quote

from sqlalchemy import select

from app.db import async_session
from app.models.material_share import (
    MaterialBookResponse,
    MaterialShareCrumb,
    MaterialShareEntry,
    MaterialShareORM,
    MaterialShareResponse,
    MaterialShelfResponse,
)
from app.services import material_service
from app.services.material_service import (
    COVER_SUFFIXES,
    _build_folder_meta,
    _normalize_materials_subpath,
    _read_meta,
    _resolve_path_in_folder,
    browse_materials,
)
from app.utils.materials import is_ebook_path, material_kind_for_path


def _page_url(public_base: str, token: str, is_dir: bool) -> str:
    kind = "shelf" if is_dir else "book"
    base = (public_base or "").rstrip("/")
    path = f"/{kind}/{token}"
    return f"{base}{path}" if base else path


def _quote_path(path: str) -> str:
    return quote(path, safe="")


def _reject_parent_segments(raw: str) -> None:
    cleaned = (raw or "").replace("\\", "/")
    if any(part == ".." for part in cleaned.split("/")):
        raise ValueError("路径超出分享范围")


def _inside(root: Path, target: Path) -> bool:
    return target == root or root in target.parents


def describe_target(sub_path: str) -> tuple[str, Path, bool]:
    rel = _normalize_materials_subpath(sub_path)
    root = material_service.get_materials_root().resolve()
    if not root.exists():
        raise ValueError("电子书目录不存在")
    target = (root / rel).resolve() if rel else root
    if not _inside(root, target):
        raise ValueError("非法路径")
    if target.is_dir():
        return rel, target, True
    if target.is_file() and is_ebook_path(target):
        return rel, target, False
    raise ValueError("只能分享目录或电子书文件")


def contain_path(share_sub_path: str, requested: str) -> str:
    _reject_parent_segments(requested)
    root_rel = _normalize_materials_subpath(share_sub_path)
    extra = _normalize_materials_subpath(requested)
    combined = f"{root_rel}/{extra}".strip("/") if extra else root_rel
    if root_rel and combined != root_rel and not combined.startswith(root_rel + "/"):
        raise ValueError("路径超出分享范围")
    materials_root = material_service.get_materials_root().resolve()
    share_base = (materials_root / root_rel).resolve() if root_rel else materials_root
    target = (materials_root / combined).resolve() if combined else materials_root
    if not _inside(share_base, target):
        raise ValueError("路径超出分享范围")
    return combined


def _relative_to_share(share_root: str, library_sub: str) -> str:
    if not share_root:
        return library_sub
    if library_sub == share_root:
        return ""
    prefix = share_root + "/"
    if not library_sub.startswith(prefix):
        raise ValueError("路径超出分享范围")
    return library_sub[len(prefix) :]


def _file_url(token: str, relative_path: str, *, is_dir: bool) -> str:
    if is_dir:
        return f"/api/v1/shelf/{token}/file?path={_quote_path(relative_path)}"
    return f"/api/v1/book/{token}/file"


class MaterialShareService:
    async def enable(self, sub_path: str, public_base: str) -> MaterialShareResponse:
        rel, _target, is_dir = describe_target(sub_path)
        async with async_session() as session:
            result = await session.execute(
                select(MaterialShareORM).where(MaterialShareORM.sub_path == rel)
            )
            row = result.scalar_one_or_none()
            if row is None:
                row = MaterialShareORM(
                    token=secrets.token_urlsafe(16),
                    sub_path=rel,
                    is_dir=is_dir,
                    enabled=True,
                )
                session.add(row)
            else:
                row.is_dir = is_dir
                row.enabled = True
            await session.commit()
            await session.refresh(row)
            return self._response(row, public_base)

    async def disable(self, sub_path: str) -> MaterialShareResponse:
        rel = _normalize_materials_subpath(sub_path)
        async with async_session() as session:
            row = await self._row_by_path(session, rel)
            if row is None:
                raise ValueError("分享不存在或已停用")
            row.enabled = False
            await session.commit()
            await session.refresh(row)
            return self._response(row, "")

    async def rotate(self, sub_path: str, public_base: str) -> MaterialShareResponse:
        rel, _target, is_dir = describe_target(sub_path)
        async with async_session() as session:
            row = await self._row_by_path(session, rel)
            if row is None:
                raise ValueError("分享不存在或已停用")
            row.token = secrets.token_urlsafe(16)
            row.is_dir = is_dir
            row.enabled = True
            await session.commit()
            await session.refresh(row)
            return self._response(row, public_base)

    async def status(self, sub_path: str, public_base: str) -> MaterialShareResponse:
        rel = _normalize_materials_subpath(sub_path)
        async with async_session() as session:
            row = await self._row_by_path(session, rel)
            if row is None or not row.enabled:
                return MaterialShareResponse(enabled=False, sub_path=rel)
            return self._response(row, public_base)

    async def resolve_share(self, token: str) -> MaterialShareORM:
        async with async_session() as session:
            result = await session.execute(
                select(MaterialShareORM).where(
                    MaterialShareORM.token == token,
                    MaterialShareORM.enabled.is_(True),
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                raise ValueError("分享不存在或已停用")
            return row

    async def list_shelf(self, token: str, relative_path: str) -> MaterialShelfResponse:
        share = await self.resolve_share(token)
        if not share.is_dir:
            raise ValueError("不是目录分享")
        library_path = contain_path(share.sub_path, relative_path)
        folder = material_service.get_materials_root().resolve()
        target = (folder / library_path).resolve() if library_path else folder
        if not target.is_dir():
            raise ValueError("目录不存在")
        listed = browse_materials("", sub_path=library_path)
        view_path = _relative_to_share(share.sub_path, library_path)
        entries: list[MaterialShareEntry] = []
        for entry in listed.entries:
            relative = _relative_to_share(share.sub_path, entry.sub_path)
            entries.append(
                MaterialShareEntry(
                    name=entry.name,
                    path=relative,
                    is_dir=entry.is_dir,
                    kind="" if entry.is_dir else entry.kind,
                    file_url="" if entry.is_dir else _file_url(token, relative, is_dir=True),
                )
            )
        meta = _read_meta(target)
        built = _build_folder_meta(target, library_path, "", "")
        cover_url = ""
        cover_name = str(meta.get("cover") or "").strip()
        if cover_name:
            cover_path = _resolve_path_in_folder(target, cover_name)
            if cover_path and cover_path.suffix.lower() in COVER_SUFFIXES:
                cover_rel = _relative_to_share(
                    share.sub_path, cover_path.relative_to(folder).as_posix()
                )
                cover_url = _file_url(token, cover_rel, is_dir=True)
        parent = None
        crumbs: list[MaterialShareCrumb] = []
        if view_path:
            parts = view_path.split("/")
            acc: list[str] = []
            for part in parts:
                acc.append(part)
                crumbs.append(MaterialShareCrumb(name=part, path="/".join(acc)))
            parent = "/".join(parts[:-1])
        return MaterialShelfResponse(
            name=built.title,
            description=built.description,
            author=built.author,
            path=view_path,
            parent=parent,
            crumbs=crumbs,
            entries=entries,
        )

    async def book_info(self, token: str) -> MaterialBookResponse:
        share = await self.resolve_share(token)
        if share.is_dir:
            raise ValueError("不是单本分享")
        path = self.share_file(share, "")
        return MaterialBookResponse(
            name=path.name,
            kind=material_kind_for_path(path),
            file_url=_file_url(token, "", is_dir=False),
        )

    async def shelf_read_info(self, token: str, relative_path: str) -> dict:
        share = await self.resolve_share(token)
        if not share.is_dir:
            raise ValueError("不是目录分享")
        path = self.share_file(share, relative_path)
        if not is_ebook_path(path):
            raise ValueError("不支持的电子书格式")
        library = contain_path(share.sub_path, relative_path)
        relative = _relative_to_share(share.sub_path, library)
        parent = "/".join(relative.split("/")[:-1]) if "/" in relative else ""
        back = f"/shelf/{token}"
        if parent:
            back = f"/shelf/{token}?path={_quote_path(parent)}"
        return {
            "name": path.name,
            "kind": material_kind_for_path(path),
            "public_url": _file_url(token, relative, is_dir=True),
            "back_href": back,
        }

    def share_file(self, share: MaterialShareORM, relative_path: str) -> Path:
        if share.is_dir:
            library = contain_path(share.sub_path, relative_path)
        else:
            if _normalize_materials_subpath(relative_path):
                raise ValueError("路径超出分享范围")
            library = share.sub_path
        root = material_service.get_materials_root().resolve()
        target = (root / library).resolve() if library else root
        share_base = (root / share.sub_path).resolve() if share.sub_path else root
        if not _inside(share_base, target):
            raise ValueError("路径超出分享范围")
        if not target.is_file():
            raise ValueError("文件不存在")
        if is_ebook_path(target) or target.suffix.lower() in COVER_SUFFIXES:
            return target
        raise ValueError("不支持的文件")

    async def open_file(self, token: str, relative_path: str) -> Path:
        share = await self.resolve_share(token)
        return self.share_file(share, relative_path)

    @staticmethod
    async def _row_by_path(session, sub_path: str) -> MaterialShareORM | None:
        result = await session.execute(
            select(MaterialShareORM).where(MaterialShareORM.sub_path == sub_path)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _response(row: MaterialShareORM, public_base: str) -> MaterialShareResponse:
        enabled = bool(row.enabled)
        return MaterialShareResponse(
            enabled=enabled,
            token=row.token if enabled else "",
            share_url=_page_url(public_base, row.token, bool(row.is_dir)) if enabled else "",
            is_dir=bool(row.is_dir),
            sub_path=row.sub_path,
        )


material_share_service = MaterialShareService()
