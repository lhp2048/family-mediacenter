import mimetypes
from pathlib import Path

_EXT_MIME = {
    ".svg": "image/svg+xml",
    ".pdf": "application/pdf",
    ".html": "text/html",
    ".htm": "text/html",
    ".md": "text/markdown",
    ".epub": "application/epub+zip",
    ".txt": "text/plain",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
}


def media_type_for_path(path: str | Path) -> str:
    target = Path(path)
    guessed, _ = mimetypes.guess_type(target.name)
    if guessed:
        return guessed
    return _EXT_MIME.get(target.suffix.lower(), "application/octet-stream")
