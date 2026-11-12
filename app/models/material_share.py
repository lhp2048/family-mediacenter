from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class MaterialShareORM(Base):
    __tablename__ = "material_shares"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    sub_path: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    is_dir: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class MaterialShareUpdate(BaseModel):
    sub_path: str = ""


class MaterialShareResponse(BaseModel):
    enabled: bool
    token: str = ""
    share_url: str = ""
    is_dir: bool = False
    sub_path: str = ""


class MaterialShareEntry(BaseModel):
    name: str
    path: str
    is_dir: bool = False
    kind: str = ""
    file_url: str = ""


class MaterialShareCrumb(BaseModel):
    name: str
    path: str


class MaterialShelfResponse(BaseModel):
    name: str
    description: str = ""
    author: str = ""
    path: str = ""
    parent: Optional[str] = None
    crumbs: list[MaterialShareCrumb] = Field(default_factory=list)
    entries: list[MaterialShareEntry] = Field(default_factory=list)


class MaterialBookResponse(BaseModel):
    name: str
    kind: str = ""
    file_url: str = ""
