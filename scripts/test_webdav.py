#!/usr/bin/env python3
"""Smoke-test embedded WebDAV (/dav) auth and read-only behavior."""
from __future__ import annotations

import base64
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _auth(user: str, password: str) -> str:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return f"Basic {token}"


def main() -> int:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.config import WebdavSettings
    from app.webdav_app import create_webdav_asgi_app, webdav_is_ready

    assert not webdav_is_ready(WebdavSettings(enabled=True, username="", password=""))
    assert webdav_is_ready(
        WebdavSettings(enabled=True, username="dav", password="secret", read_only=True)
    )

    storage = ROOT / "downloads"
    storage.mkdir(parents=True, exist_ok=True)
    (storage / "multimedia").mkdir(exist_ok=True)
    (storage / "ebooks").mkdir(exist_ok=True)
    probe = storage / "_webdav_probe.txt"
    if probe.exists():
        probe.unlink()

    ro = WebdavSettings(
        enabled=True, username="dav", password="secret", read_only=True
    )
    app = FastAPI()
    app.mount("/dav", create_webdav_asgi_app(ro))
    client = TestClient(app)

    bad = client.request(
        "PROPFIND",
        "/dav/",
        headers={"Depth": "1", "Authorization": _auth("dav", "wrong")},
    )
    assert bad.status_code in (401, 403), bad.status_code

    ok = client.request(
        "PROPFIND",
        "/dav/",
        headers={"Depth": "1", "Authorization": _auth("dav", "secret")},
    )
    assert ok.status_code == 207, (ok.status_code, ok.text[:300])
    hrefs = re.findall(r"<[^>]*href>([^<]+)</", ok.text, re.I)
    assert any("/dav/multimedia" in h for h in hrefs), hrefs
    assert any("/dav/ebooks" in h for h in hrefs), hrefs

    put_ro = client.put(
        "/dav/_webdav_probe.txt",
        content=b"nope",
        headers={"Authorization": _auth("dav", "secret")},
    )
    assert put_ro.status_code in (403, 405, 409, 500) or put_ro.status_code >= 400, (
        put_ro.status_code,
        put_ro.text[:200],
    )
    assert not probe.exists(), "read-only must not create file"

    rw = WebdavSettings(
        enabled=True, username="dav", password="secret", read_only=False
    )
    app_rw = FastAPI()
    app_rw.mount("/dav", create_webdav_asgi_app(rw))
    client_rw = TestClient(app_rw)
    put_rw = client_rw.put(
        "/dav/_webdav_probe.txt",
        content=b"webdav-ok\n",
        headers={"Authorization": _auth("dav", "secret")},
    )
    assert put_rw.status_code in (200, 201, 204), (put_rw.status_code, put_rw.text[:200])
    assert probe.is_file() and probe.read_bytes() == b"webdav-ok\n"

    deleted = client_rw.delete(
        "/dav/_webdav_probe.txt",
        headers={"Authorization": _auth("dav", "secret")},
    )
    assert deleted.status_code in (200, 204), deleted.status_code
    assert not probe.exists()

    print("OK: webdav propfind/auth/readonly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
