from pathlib import Path

EBOOK_EXT = {".md", ".pdf", ".epub", ".txt"}


def is_ebook_path(path: str | Path) -> bool:
    return Path(path).suffix.lower() in EBOOK_EXT


def is_material_path(path: str | Path) -> bool:
    return is_ebook_path(path)


def content_kind_for_path(path: str | Path | None) -> str:
    if not path:
        return ""
    ext = Path(path).suffix.lower()
    if ext == ".md":
        return "markdown"
    if ext == ".pdf":
        return "pdf"
    if ext == ".epub":
        return "epub"
    if ext == ".txt":
        return "text"
    return ""


def material_kind_for_path(path: str | Path) -> str:
    kind = content_kind_for_path(path)
    return kind or "ebook"
