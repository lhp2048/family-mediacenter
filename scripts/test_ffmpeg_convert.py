#!/usr/bin/env python3
"""Smoke-test ffmpeg resolve + optional real convert to *_compat.mp4."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from app.config import resolve_ffmpeg_executable, resolve_ffprobe_executable
    from app.services.engine_status import get_ffmpeg_status

    ffmpeg = resolve_ffmpeg_executable("ffmpeg")
    print(f"resolve_ffmpeg_executable -> {ffmpeg}")
    status = asyncio.run(get_ffmpeg_status())
    print(f"ffmpeg status: available={status.available} version={status.version!r} msg={status.message}")

    if not status.available or not Path(ffmpeg).is_file():
        print("SKIP: ffmpeg not installed; config/status path only")
        return 0

    media = ROOT / "downloads" / "multimedia"
    media.mkdir(parents=True, exist_ok=True)
    sample = media / "_ffmpeg_smoke_src.mp4"
    compat = media / "_ffmpeg_smoke_src_compat.mp4"
    for p in (sample, compat):
        if p.exists():
            p.unlink()

    # Generate a tiny synthetic clip (1 frame-ish / 0.5s)
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=blue:s=160x120:d=0.5",
        "-f",
        "lavfi",
        "-i",
        "sine=f=440:d=0.5",
        "-c:v",
        "mpeg4",
        "-c:a",
        "mp2",
        "-shortest",
        str(sample),
    ]
    import subprocess

    gen = subprocess.run(cmd, capture_output=True, text=True)
    if gen.returncode != 0:
        print("SKIP: could not synthesize sample:", (gen.stderr or "")[-400:])
        return 0

    from app.db import init_db
    from app.services.ffmpeg_convert import convert_service

    asyncio.run(init_db())

    async def run_convert():
        job = await convert_service.start_job(rel_path=sample.name, public_base="http://127.0.0.1:18026")
        for _ in range(120):
            j = convert_service.get_job(job.id)
            assert j is not None
            if j.status in ("completed", "failed", "skipped"):
                return j
            await asyncio.sleep(0.25)
        return convert_service.get_job(job.id)

    job = asyncio.run(run_convert())
    assert job is not None
    print("job:", job.to_dict())
    if job.status == "failed":
        # Already-compat may remux; failure is a hard fail
        print("FAIL:", job.message)
        return 1

    assert compat.is_file(), f"missing {compat}"
    assert sample.is_file(), "original should be kept"
    print("OK: compat file written, original kept")
    # cleanup
    sample.unlink(missing_ok=True)
    compat.unlink(missing_ok=True)
    ffprobe = resolve_ffprobe_executable(ffmpeg)
    print(f"ffprobe -> {ffprobe} exists={Path(ffprobe).is_file()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
