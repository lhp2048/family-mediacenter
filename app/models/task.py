import enum
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field
from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SourceType(str, enum.Enum):
    YTDLP = "ytdlp"
    ARIA2 = "aria2"
    ALIST = "alist"
    DIRECT = "direct"


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class TaskORM(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(String(512), default="")
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=TaskStatus.PENDING.value)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    speed: Mapped[str] = mapped_column(String(64), default="")
    file_path: Mapped[str] = mapped_column(Text, default="")
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    engine_task_id: Mapped[str] = mapped_column(String(128), default="")
    options_json: Mapped[str] = mapped_column(Text, default="{}")
    output_dir: Mapped[str] = mapped_column(Text, default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class TaskCreate(BaseModel):
    url: str
    engine: Optional[str] = None
    options: dict[str, Any] = Field(default_factory=dict)
    output_dir: Optional[str] = None


class TaskResponse(BaseModel):
    id: int
    url: str
    title: str = ""
    source_type: str
    status: str
    progress: float = 0.0
    speed: str = ""
    file_path: str = ""
    file_size: int = 0
    engine_task_id: str = ""
    options: dict[str, Any] = Field(default_factory=dict)
    output_dir: str = ""
    error_message: str = ""
    log_available: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SettingsUpdate(BaseModel):
    server: Optional[dict[str, Any]] = None
    download: Optional[dict[str, Any]] = None
    files: Optional[dict[str, Any]] = None
    webdav: Optional[dict[str, Any]] = None
    materials: Optional[dict[str, Any]] = None
    integration: Optional[dict[str, Any]] = None
    tvbox: Optional[dict[str, Any]] = None
    engines: Optional[dict[str, Any]] = None
