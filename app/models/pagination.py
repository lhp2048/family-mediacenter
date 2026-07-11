from math import ceil
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

DEFAULT_PAGE_SIZE = 15
MAX_PAGE_SIZE = 100


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    page_size: int = DEFAULT_PAGE_SIZE
    total_pages: int = 0

    @classmethod
    def from_items(
        cls,
        items: list[T],
        total: int,
        page: int,
        page_size: int,
    ) -> "PaginatedResponse[T]":
        pages = ceil(total / page_size) if page_size > 0 and total > 0 else (1 if total == 0 else 0)
        if total > 0 and pages == 0:
            pages = 1
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=pages,
        )


def normalize_page(page: int) -> int:
    return max(1, page)


def normalize_page_size(page_size: int) -> int:
    return max(1, min(page_size, MAX_PAGE_SIZE))
