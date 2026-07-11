from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class TvboxSourceORM(Base):
    __tablename__ = "tvbox_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(Text, default="")
    last_test_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_test_ok: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    last_test_message: Mapped[str] = mapped_column(Text, default="")
    last_test_latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_test_summary: Mapped[str] = mapped_column(Text, default="")
    last_test_detail: Mapped[str] = mapped_column(Text, default="")
    last_test_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_test_grade: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class TvboxSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    url: str = Field(min_length=4)
    enabled: bool = True
    note: str = ""


class TvboxSourceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    url: Optional[str] = Field(None, min_length=4)
    enabled: Optional[bool] = None
    note: Optional[str] = None
    sort_order: Optional[int] = None


class TvboxSourceResponse(BaseModel):
    id: int
    name: str
    url: str
    enabled: bool
    sort_order: int
    note: str = ""
    last_test_at: Optional[datetime] = None
    last_test_ok: Optional[bool] = None
    last_test_message: str = ""
    last_test_latency_ms: Optional[int] = None
    last_test_summary: str = ""
    last_test_detail: dict[str, Any] = Field(default_factory=dict)
    last_test_score: Optional[int] = None
    last_test_grade: str = ""
    created_at: Optional[datetime] = None


class TvboxSourceTestResult(BaseModel):
    id: int
    name: str
    url: str
    ok: bool
    http_status: Optional[int] = None
    latency_ms: Optional[int] = None
    message: str = ""
    summary: dict[str, Any] = Field(default_factory=dict)
    detail: dict[str, Any] = Field(default_factory=dict)
    last_test_at: Optional[datetime] = None
    last_test_summary: str = ""


class TvboxFeedInfo(BaseModel):
    feed_url: str
    source_count: int
    enabled_count: int
    title: str = "Family Media Center TVBox 多合一"


class TvboxReorderItem(BaseModel):
    id: int
    sort_order: int
