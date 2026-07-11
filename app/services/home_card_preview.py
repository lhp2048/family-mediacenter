"""Home card preview for mediacenter-owned modules (ebook)."""

from __future__ import annotations

from datetime import datetime

from app.services.file_manager import get_public_base_url
from app.services.material_service import browse_materials


def _count_ebook_files(public_base: str) -> tuple[int, list[str]]:
    try:
        data = browse_materials(public_base, sub_path="", page=1, page_size=100)
    except ValueError:
        return 0, []
    names: list[str] = []
    for entry in data.entries:
        if entry.is_dir:
            continue
        name = (entry.name or "").strip()
        if name:
            names.append(name)
    total = data.total if data.total is not None else len(names)
    return int(total), names


def build_ebook_home_preview(size: str, *, public_base: str) -> dict:
    normalized = (size or "medium").strip().lower()
    total, names = _count_ebook_files(public_base)
    now = datetime.now().isoformat()
    if normalized == "small":
        presentation: dict = {
            "type": "compact",
            "badge": str(total) if total > 0 else None,
            "hint": names[0][:40] if names else "暂无图书",
        }
    elif normalized == "medium":
        rows = [{"label": n[:40], "value": ""} for n in names[:3]]
        if total > 0 and not rows:
            rows = [{"label": f"共 {total} 本", "value": ""}]
        presentation = {"type": "rows", "rows": rows}
    else:
        rows = [{"label": n[:40], "value": ""} for n in names[:6]]
        footer = f"共 {total} 本" if total > 0 else None
        presentation = {"type": "rows", "rows": rows, "footer": footer}

    return {
        "cardId": "ebook",
        "size": normalized,
        "title": "电子图书",
        "subtitle": "家庭书库 · 在线阅读",
        "updatedAt": now,
        "presentation": presentation,
    }


def build_home_card_preview(card_id: str, size: str, *, request_base: str) -> dict:
    cid = (card_id or "").strip().lower()
    public_base = get_public_base_url(request_base.rstrip("/"))
    if cid == "ebook":
        return build_ebook_home_preview(size, public_base=public_base)
    raise ValueError(f"未知的 cardId: {card_id}")
