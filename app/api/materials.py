from fastapi import APIRouter, HTTPException, Query, Request

from app.models.pagination import DEFAULT_PAGE_SIZE
from app.services.file_manager import get_public_base_url
from app.services.material_service import browse_materials

router = APIRouter(tags=["materials"])


def _public_base(request: Request) -> str:
    return get_public_base_url(str(request.base_url).rstrip("/"))


@router.get("/api/v1/materials")
async def api_browse_materials(
    request: Request,
    path: str = Query("", description="相对书库根目录的路径"),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=100),
) -> dict:
    try:
        data = browse_materials(
            _public_base(request),
            sub_path=path,
            page=page,
            page_size=page_size,
        )
        return data.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
