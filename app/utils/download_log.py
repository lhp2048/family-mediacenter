from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable

from app.config import LOGS_DIR


def log_path_for_task(task_id: int) -> Path:
    return LOGS_DIR / f"download_{task_id}.log"


def download_log_exists(task_id: int) -> bool:
    return log_path_for_task(task_id).is_file()


def init_download_log(
    task_id: int,
    *,
    engine: str,
    url: str,
    cmd: Iterable[str] | None = None,
) -> Path:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    path = log_path_for_task(task_id)
    lines = [
        f"# task_id={task_id} engine={engine}",
        f"# started={datetime.utcnow().isoformat()}Z",
        f"# url={url}",
    ]
    if cmd:
        lines.append(f"# cmd={' '.join(cmd)}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def append_download_log(task_id: int, line: str) -> None:
    path = log_path_for_task(task_id)
    if not path.is_file():
        return
    with path.open("a", encoding="utf-8") as f:
        f.write(line)
        if not line.endswith("\n"):
            f.write("\n")


def finalize_download_log(task_id: int, *, return_code: int | None = None) -> None:
    path = log_path_for_task(task_id)
    if not path.is_file():
        return
    suffix = f"\n# exit_code={return_code}\n" if return_code is not None else "\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(suffix)


def remove_download_log(task_id: int) -> None:
    path = log_path_for_task(task_id)
    if path.is_file():
        path.unlink()


def write_download_log(
    task_id: int,
    lines: Iterable[str],
    *,
    engine: str,
    url: str = "",
    header: str = "",
) -> Path:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    path = log_path_for_task(task_id)
    body = list(lines)
    parts = [
        f"# task_id={task_id} engine={engine}",
        f"# written={datetime.utcnow().isoformat()}Z",
    ]
    if url:
        parts.append(f"# url={url}")
    if header:
        parts.append(f"# {header}")
    parts.append("")
    parts.extend(body)
    path.write_text("\n".join(parts), encoding="utf-8")
    return path


def read_download_log(task_id: int) -> str | None:
    path = log_path_for_task(task_id)
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def log_api_path(task_id: int) -> str:
    return f"/api/v1/tasks/{task_id}/log"
