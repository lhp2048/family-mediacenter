from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ShareDeviceORM(Base):
    __tablename__ = "share_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    visitor_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    device_label: Mapped[str] = mapped_column(String(128), default="")
    user_agent: Mapped[str] = mapped_column(Text, default="")
    last_ip: Mapped[str] = mapped_column(String(64), default="")
    allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    eye_watched_sec: Mapped[float] = mapped_column(Float, default=0.0)
    eye_last_play_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    eye_locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class ShareVisitORM(Base):
    __tablename__ = "share_visits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("share_devices.id", ondelete="CASCADE"), nullable=False
    )
    playlist_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("playlists.id", ondelete="CASCADE"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(Text, default="")
    device_label: Mapped[str] = mapped_column(String(128), default="")


class SharePlaybackORM(Base):
    __tablename__ = "share_playbacks"
    __table_args__ = (
        UniqueConstraint(
            "visit_id",
            "item_id",
            "day",
            "hour",
            name="uq_share_playback_bucket",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    visit_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("share_visits.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("share_devices.id", ondelete="CASCADE"), nullable=False
    )
    playlist_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("playlists.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(512), default="")
    day: Mapped[str] = mapped_column(String(10), nullable=False)
    hour: Mapped[int] = mapped_column(Integer, nullable=False)
    watch_sec: Mapped[float] = mapped_column(Float, default=0.0)
    play_count: Mapped[int] = mapped_column(Integer, default=0)
    complete_count: Mapped[int] = mapped_column(Integer, default=0)
    first_played_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_played_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class ShareStatEvent(BaseModel):
    type: str
    item_id: int
    delta_sec: float = 0.0


class ShareDeviceAccessUpdate(BaseModel):
    allowed: bool


class ShareEyeCareORM(Base):
    __tablename__ = "share_eye_care"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    play_minutes: Mapped[int] = mapped_column(Integer, default=30)
    rest_minutes: Mapped[int] = mapped_column(Integer, default=15)


class ShareEyeCareUpdate(BaseModel):
    enabled: bool = True
    play_minutes: int = Field(default=30, ge=1, le=240)
    rest_minutes: int = Field(default=15, ge=1, le=180)


class ShareEyeCareResponse(BaseModel):
    enabled: bool = True
    play_minutes: int = 30
    rest_minutes: int = 15


class ShareHourStat(BaseModel):
    hour: int
    watch_sec: float = 0.0


class ShareDayStat(BaseModel):
    date: str
    watch_sec: float = 0.0
    first_at: Optional[datetime] = None
    last_at: Optional[datetime] = None
    hours: list[ShareHourStat] = Field(default_factory=list)


class ShareHotItem(BaseModel):
    item_id: int
    title: str = ""
    watch_sec: float = 0.0
    play_count: int = 0
    complete_count: int = 0


class ShareDeviceStat(BaseModel):
    id: int
    device_label: str = ""
    last_ip: str = ""
    user_agent: str = ""
    allowed: bool = True
    watch_sec: float = 0.0
    by_day: list[ShareDayStat] = Field(default_factory=list)
    hot_items: list[ShareHotItem] = Field(default_factory=list)


class ShareStatsResponse(BaseModel):
    from_date: str
    to_date: str
    devices: list[ShareDeviceStat] = Field(default_factory=list)


class ShareDeviceResponse(BaseModel):
    id: int
    device_label: str = ""
    last_ip: str = ""
    user_agent: str = ""
    allowed: bool = True
