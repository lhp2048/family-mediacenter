from fastapi import APIRouter, HTTPException, Query, Request

from app.services.home_card_preview import build_home_card_preview

router = APIRouter(tags=["home-cards"])


@router.get("/api/v1/home/cards/ebook")
async def home_card_ebook(
    request: Request,
    size: str = Query("medium"),
) -> dict:
    try:
        base = str(request.base_url).rstrip("/")
        return build_home_card_preview("ebook", size, request_base=base)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/api/v1/home/cards/{card_id}")
async def home_card_preview(
    request: Request,
    card_id: str,
    size: str = Query("medium"),
) -> dict:
    if card_id.strip().lower() == "ebook":
        return await home_card_ebook(request, size=size)
    raise HTTPException(status_code=404, detail=f"未知的 cardId: {card_id}")
