"""Stream an upload into a new file. Existing names and symlinks are left untouched."""

import os
from pathlib import Path

from fastapi import UploadFile

MAX_UPLOAD_BYTES = 8 * 1024 * 1024 * 1024


async def write_new_file(
    dest: Path,
    upload: UploadFile,
    *,
    max_bytes: int = MAX_UPLOAD_BYTES,
) -> int:
    if dest.is_symlink() or dest.exists():
        raise ValueError("同名文件已存在")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.parent / f".{dest.name}.{os.getpid()}.uploading"
    size = 0
    try:
        with tmp.open("xb") as handle:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError("文件过大")
                handle.write(chunk)
        if size == 0:
            raise ValueError("文件是空的")
        try:
            os.link(tmp, dest)
        except FileExistsError as exc:
            raise ValueError("同名文件已存在") from exc
    finally:
        tmp.unlink(missing_ok=True)
    return size
