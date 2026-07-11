#!/usr/bin/env python3
"""Family Media Center local dev server with hot reload."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("PYTHONUNBUFFERED", "1")

import uvicorn  # noqa: E402

from app.config import load_settings  # noqa: E402


def main() -> None:
    settings = load_settings()
    host = os.environ.get("MEDIACENTER_DEV_HOST", "127.0.0.1")
    port = int(os.environ.get("MEDIACENTER_DEV_PORT", str(settings.server.port)))
    reload = os.environ.get("MEDIACENTER_DEV_RELOAD", "1") != "0"

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload,
        reload_dirs=[str(ROOT / "app")],
        log_level="info",
        access_log=True,
    )


if __name__ == "__main__":
    main()
