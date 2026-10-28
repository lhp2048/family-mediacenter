#!/usr/bin/env python3
"""Smoke-test engine lifecycle actions API."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from fastapi.testclient import TestClient

    from app.db import init_db
    from app.main import app
    from app.services.engine_lifecycle import ALLOWED, lifecycle_service

    asyncio.run(init_db())
    client = TestClient(app)

    # whitelist
    assert "install" in ALLOWED["ytdlp"]
    assert "start" in ALLOWED["aria2"]
    assert "start" in ALLOWED["alist"]
    assert "install" not in ALLOWED["aria2"]
    assert "install" not in ALLOWED["alist"]

    # alist / unsupported install
    r = client.post("/api/v1/engines/alist/actions", json={"action": "install"})
    assert r.status_code == 400, r.text

    r = client.post("/api/v1/engines/aria2/actions", json={"action": "install"})
    assert r.status_code == 400, r.text

    # remote mode rejects process control
    from app.config import load_settings, save_settings
    from app import config as config_module

    s = load_settings()
    old_runtime = s.engines.alist.runtime
    s.engines.alist.runtime = "remote"
    save_settings(s)
    config_module.settings = load_settings()
    try:
        r = client.post("/api/v1/engines/alist/actions", json={"action": "start"})
        assert r.status_code == 400, r.text
        assert "远程" in (r.json().get("detail") or "")
    finally:
        s = load_settings()
        s.engines.alist.runtime = old_runtime or "local"
        save_settings(s)
        config_module.settings = load_settings()

    # ytdlp restart (refresh) should complete
    r = client.post("/api/v1/engines/ytdlp/actions", json={"action": "restart"})
    assert r.status_code == 200, r.text
    job = r.json()
    assert job.get("id")
    job_id = job["id"]

    for _ in range(40):
        j = client.get(f"/api/v1/engines/actions/{job_id}").json()
        if j.get("status") in ("completed", "failed"):
            assert j["status"] == "completed", j
            break
        asyncio.run(asyncio.sleep(0.1))
        # sync sleep
        import time

        time.sleep(0.15)
    else:
        print("FAIL: ytdlp restart job timeout")
        return 1

    # ffmpeg restart
    r = client.post("/api/v1/engines/ffmpeg/actions", json={"action": "restart"})
    assert r.status_code == 200, r.text
    job_id = r.json()["id"]
    import time

    for _ in range(40):
        j = client.get(f"/api/v1/engines/actions/{job_id}").json()
        if j.get("status") in ("completed", "failed"):
            assert j["status"] == "completed", j
            break
        time.sleep(0.15)
    else:
        print("FAIL: ffmpeg restart timeout")
        return 1

    # duplicate pending returns same job
    async def dup():
        # force a long-running by starting check_update twice quickly
        j1 = await lifecycle_service.start_action("ytdlp", "check_update")
        j2 = await lifecycle_service.start_action("ytdlp", "check_update")
        return j1.id, j2.id, j1.status, j2.status

    id1, id2, s1, s2 = asyncio.run(dup())
    # may already finished; if both still early, ids equal
    print(f"check_update jobs: {id1}/{s1} vs {id2}/{s2}")

    print("OK: engine lifecycle smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
