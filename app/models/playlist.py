from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


DEFAULT_PLAYLIST_NAME = "全部下载"


class PlaylistORM(Base):
    __tablename__ = "playlists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    share_token: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True)
    share_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    share_last_item_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    share_position_sec: Mapped[float] = mapped_column(Float, default=0.0)
    share_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    share_autoplay: Mapped[bool] = mapped_column(Boolean, default=False)

    items: Mapped[list["PlaylistItemORM"]] = relationship(
        "PlaylistItemORM",
        back_populates="playlist",
        cascade="all, delete-orphan",
        order_by="PlaylistItemORM.sort_order",
    )


class PlaylistItemORM(Base):
    __tablename__ = "playlist_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    playlist_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("playlists.id", ondelete="CASCADE"), nullable=False
    )
    rel_path: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(String(512), default="")
    task_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    added_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    playlist: Mapped["PlaylistORM"] = relationship("PlaylistORM", back_populates="items")


class PlaylistCreate(BaseModel):
    name: str = Field(min_length=1, max_length=256)


class PlaylistItemCreate(BaseModel):
    rel_path: Optional[str] = None
    task_id: Optional[int] = None


class PlaylistItemBulkDelete(BaseModel):
    item_ids: list[int] = Field(default_factory=list, min_length=1)


class PlaylistItemReorder(BaseModel):
    id: int
    sort_order: int


class PlaylistAutoplayUpdate(BaseModel):
    autoplay: bool


class PlaylistProgressUpdate(BaseModel):
    item_id: int
    position_sec: float = 0.0


class PlaylistItemResponse(BaseModel):
    id: int
    playlist_id: int
    rel_path: str
    title: str = ""
    name: str = ""
    size: int = 0
    media_type: str = ""
    task_id: Optional[int] = None
    sort_order: int = 0
    public_url: str = ""
    exists: bool = True
    info_ready: bool = True
    added_at: Optional[datetime] = None


class PlaylistResponse(BaseModel):
    id: int
    name: str
    is_default: bool = False
    item_count: int = 0
    created_at: Optional[datetime] = None
    share_enabled: bool = False
    share_token: str = ""
    share_url: str = ""
    share_autoplay: bool = False
    share_last_item_id: Optional[int] = None
    share_position_sec: float = 0.0
    share_updated_at: Optional[datetime] = None


class PlaylistShareResponse(BaseModel):
    share_enabled: bool
    share_token: str = ""
    share_url: str = ""
    share_autoplay: bool = False


class WatchProgress(BaseModel):
    item_id: int
    position_sec: float = 0.0
    updated_at: Optional[datetime] = None


class WatchItemResponse(BaseModel):
    id: int
    title: str = ""
    media_type: str = ""
    public_url: str = ""
    sort_order: int = 0


class WatchPlaylistResponse(BaseModel):
    name: str
    autoplay: bool = False
    items: list[WatchItemResponse] = Field(default_factory=list)
    progress: Optional[WatchProgress] = None


class PlaylistReloadResult(BaseModel):
    added: int = 0
    removed: int = 0
    item_count: int = 0
    message: str = ""


class PlaylistRenameReplaceRequest(BaseModel):
    find: str = Field(min_length=1, description="文件名中要查找的字符串")
    replace: str = Field(default="", description="替换为（可为空，表示删除匹配段）")
    dry_run: bool = False


class PlaylistRenameReplaceItem(BaseModel):
    old_rel_path: str
    new_rel_path: str
    old_name: str = ""
    new_name: str = ""
    refs_updated: int = 0


class PlaylistRenameReplaceResult(BaseModel):
    ok: bool = True
    dry_run: bool = False
    find: str = ""
    replace: str = ""
    renamed: list[PlaylistRenameReplaceItem] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    message: str = ""
