from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class TvboxTestRunORM(Base):
    __tablename__ = "tvbox_test_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mode: Mapped[str] = mapped_column(String(16), default="quick")
    status: Mapped[str] = mapped_column(String(32), default="running")
    source_count: Mapped[int] = mapped_column(Integer, default=0)
    ok_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class TvboxTestReportORM(Base):
    __tablename__ = "tvbox_test_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(16), default="quick")
    ok: Mapped[bool] = mapped_column(Boolean, default=False)
    score: Mapped[int] = mapped_column(Integer, default=0)
    grade: Mapped[str] = mapped_column(String(32), default="unknown")
    availability: Mapped[str] = mapped_column(String(32), default="unknown")
    message: Mapped[str] = mapped_column(Text, default="")
    report_json: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class TvboxTestReportResponse(BaseModel):
    id: int
    source_id: int
    run_id: Optional[int] = None
    mode: str = "quick"
    ok: bool = False
    score: int = 0
    grade: str = "unknown"
    availability: str = "unknown"
    message: str = ""
    report: dict = Field(default_factory=dict)
    created_at: Optional[datetime] = None


class TvboxTestReportSummary(BaseModel):
    id: int
    source_id: int
    mode: str = "quick"
    ok: bool = False
    score: int = 0
    grade: str = "unknown"
    availability: str = "unknown"
    message: str = ""
    created_at: Optional[datetime] = None
