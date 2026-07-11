from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class MaterialBrowseEntry(BaseModel):
    name: str
    sub_path: str
    rel_path: str
    is_dir: bool
    kind: str = ""
    size: int = 0
    modified_at: Optional[datetime] = None
    public_url: str = ""


class MaterialFolderMeta(BaseModel):
    title: str = ""
    description: str = ""
    author: str = ""
    tags: list[str] = []
    cover_url: str = ""


class MaterialBrowseResponse(BaseModel):
    root: str
    dir: str
    path: str
    parent: str
    folder: MaterialFolderMeta
    entries: list[MaterialBrowseEntry]
    total: int = 0
    page: int = 1
    page_size: int = 15
    total_pages: int = 0
