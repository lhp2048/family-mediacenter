from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ShareReadVisitORM(Base):
    __tablename__ = "share_read_visits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("share_devices.id", ondelete="CASCADE"), nullable=False
    )
    token: Mapped[str] = mapped_column(String(64), nullable=False)
    book_path: Mapped[str] = mapped_column(String(1024), default="")
    title: Mapped[str] = mapped_column(String(512), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(Text, default="")
    device_label: Mapped[str] = mapped_column(String(128), default="")
    opened: Mapped[bool] = mapped_column(Boolean, default=False)


class ShareReadORM(Base):
    __tablename__ = "share_reads"
    __table_args__ = (
        UniqueConstraint("visit_id", "day", "hour", name="uq_share_read_bucket"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    visit_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("share_read_visits.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("share_devices.id", ondelete="CASCADE"), nullable=False
    )
    token: Mapped[str] = mapped_column(String(64), nullable=False)
    book_path: Mapped[str] = mapped_column(String(1024), default="")
    title: Mapped[str] = mapped_column(String(512), default="")
    day: Mapped[str] = mapped_column(String(10), nullable=False)
    hour: Mapped[int] = mapped_column(Integer, nullable=False)
    read_sec: Mapped[float] = mapped_column(Float, default=0.0)
    open_count: Mapped[int] = mapped_column(Integer, default=0)
    first_read_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_read_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class ShareReadEvent(BaseModel):
    type: str
    delta_sec: float = 0.0
    visit_id: Optional[int] = None


class ShareReadHourStat(BaseModel):
    hour: int
    read_sec: float = 0.0


class ShareReadDayStat(BaseModel):
    date: str
    read_sec: float = 0.0
    first_at: Optional[datetime] = None
    last_at: Optional[datetime] = None
    hours: list[ShareReadHourStat] = Field(default_factory=list)


class ShareHotBook(BaseModel):
    path: str
    title: str = ""
    read_sec: float = 0.0
    open_count: int = 0


class ShareReadDeviceStat(BaseModel):
    id: int
    device_label: str = ""
    last_ip: str = ""
    user_agent: str = ""
    allowed: bool = True
    read_sec: float = 0.0
    by_day: list[ShareReadDayStat] = Field(default_factory=list)
    hot_books: list[ShareHotBook] = Field(default_factory=list)


class ShareReadStatsResponse(BaseModel):
    from_date: str
    to_date: str
    devices: list[ShareReadDeviceStat] = Field(default_factory=list)
