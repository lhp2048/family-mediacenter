#!/usr/bin/env python3
"""yt-dlp default format prefers a progressive H.264+AAC MP4."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.engines.ytdlp import COMPAT_VIDEO_FORMAT, YtDlpEngine  # noqa: E402


def test_default_cmd_requests_standard_mp4() -> None:
    engine = YtDlpEngine()
    cmd = engine._build_cmd("https://example.com/watch", "/tmp/out", 7, {})
    assert COMPAT_VIDEO_FORMAT in cmd
    assert cmd[cmd.index("--merge-output-format") + 1] == "mp4"
    assert cmd[cmd.index("--remux-video") + 1] == "mp4"
    assert "ffmpeg:-movflags +faststart" in cmd
    assert "vcodec:h264,res,acodec:aac" in cmd


def test_audio_and_custom_format_keep_their_selector() -> None:
    engine = YtDlpEngine()
    audio = engine._build_cmd("https://example.com/a", "/tmp/out", 8, {"audio_only": True})
    assert "--audio-format" in audio and "mp3" in audio
    assert "--remux-video" not in audio

    custom = engine._build_cmd(
        "https://example.com/v", "/tmp/out", 9, {"format": "bestvideo+bestaudio"}
    )
    assert "bestvideo+bestaudio" in custom
    assert "--remux-video" not in custom


def test_find_latest_prefers_merged_mp4() -> None:
    engine = YtDlpEngine()
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        frag = base / "task_3_title.f137.mp4"
        merged = base / "task_3_title.mp4"
        webm = base / "task_3_title.webm"
        sub = base / "task_3_title.vtt"
        part = base / "task_3_title.mp4.part"
        for path in (merged, frag, webm, sub, part):
            path.write_bytes(b"x")
        found = engine._find_latest_file(tmp, 3)
        assert Path(found).name == "task_3_title.mp4"

        merged.unlink()
        frag.unlink()
        found_webm = engine._find_latest_file(tmp, 3)
        assert Path(found_webm).name == "task_3_title.webm"


def main() -> int:
    test_default_cmd_requests_standard_mp4()
    test_audio_and_custom_format_keep_their_selector()
    test_find_latest_prefers_merged_mp4()
    print("OK: yt-dlp format selection")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
