#!/usr/bin/env python3
"""Smoke-test Content-Disposition for GET /files/...?download=1."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from fastapi.testclient import TestClient

    from app.config import PROJECT_ROOT
    from app.main import app

    ebooks = PROJECT_ROOT / "downloads" / "ebooks"
    ebooks.mkdir(parents=True, exist_ok=True)
    probe = ebooks / "_download_probe.txt"
    probe.write_text("download-probe\n", encoding="utf-8")
    rel = "ebooks/_download_probe.txt"

    try:
        client = TestClient(app)

        inline = client.get(f"/files/{rel}")
        assert inline.status_code == 200, inline.status_code
        cd_inline = inline.headers.get("content-disposition", "")
        assert "attachment" not in cd_inline.lower(), cd_inline

        forced = client.get(f"/files/{rel}", params={"download": "1"})
        assert forced.status_code == 200, forced.status_code
        cd = forced.headers.get("content-disposition", "")
        assert "attachment" in cd.lower(), cd
        assert "_download_probe.txt" in cd, cd
        assert forced.content == b"download-probe\n"

        for val in ("true", "TRUE"):
            r = client.get(f"/files/{rel}", params={"download": val})
            assert r.status_code == 200
            assert "attachment" in r.headers.get("content-disposition", "").lower()

        for val in ("0", "false", ""):
            r = client.get(f"/files/{rel}", params={"download": val})
            assert r.status_code == 200
            assert "attachment" not in r.headers.get("content-disposition", "").lower()

        print("OK: download disposition behavior")
        return 0
    finally:
        try:
            probe.unlink(missing_ok=True)
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
