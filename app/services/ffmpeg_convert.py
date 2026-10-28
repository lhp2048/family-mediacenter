"""Manual H.264+AAC compat conversion via ffmpeg (background jobs)."""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import update

from app.config import (
    load_settings,
    resolve_ffmpeg_executable,
    resolve_ffprobe_executable,
)
from app.db import async_session
from app.models.playlist import PlaylistItemORM
from app.services.file_manager import build_public_url, to_storage_rel
from app.utils.encoding import decode_bytes, subprocess_env
from app.utils.media import is_media_path, media_type_for_path, resolve_media_rel_path, to_rel_path

logger = logging.getLogger(__name__)


@dataclass
class ConvertJob:
    id: str
    status: str = "pending"  # pending|running|completed|failed|skipped
    message: str = ""
    source_rel: str = ""
    output_rel: str = ""
    public_url: str = ""
    playlist_id: Optional[int] = None
    item_id: Optional[int] = None
    updated_items: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "message": self.message,
            "source": self.source_rel,
            "output": self.output_rel,
            "public_url": self.public_url,
            "playlist_id": self.playlist_id,
            "item_id": self.item_id,
            "updated_items": self.updated_items,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "ok": self.status in ("completed", "skipped"),
        }


class FFmpegConvertService:
    def __init__(self) -> None:
        self._jobs: dict[str, ConvertJob] = {}
        self._lock = asyncio.Lock()

    def get_job(self, job_id: str) -> Optional[ConvertJob]:
        return self._jobs.get(job_id)

    async def start_job(
        self,
        *,
        rel_path: Optional[str] = None,
        playlist_id: Optional[int] = None,
        item_id: Optional[int] = None,
        public_base: str = "",
    ) -> ConvertJob:
        source_rel = (rel_path or "").strip()
        if item_id is not None:
            async with async_session() as session:
                item = await session.get(PlaylistItemORM, item_id)
                if not item:
                    raise ValueError(f"播放列表条目不存在: {item_id}")
                if playlist_id is not None and item.playlist_id != playlist_id:
                    raise ValueError("playlist_id 与 item_id 不匹配")
                source_rel = item.rel_path
                playlist_id = item.playlist_id

        if not source_rel:
            raise ValueError("请提供 rel_path 或 playlist_id+item_id")

        if source_rel.endswith("_compat.mp4") or Path(source_rel).stem.endswith("_compat"):
            raise ValueError("该文件已是兼容格式")

        src = resolve_media_rel_path(source_rel)
        if not src.is_file():
            raise ValueError(f"文件不存在: {source_rel}")
        if not is_media_path(src):
            raise ValueError("仅支持音视频文件转码")

        job = ConvertJob(
            id=uuid.uuid4().hex[:12],
            source_rel=source_rel,
            playlist_id=playlist_id,
            item_id=item_id,
            status="pending",
            message="排队中",
        )
        async with self._lock:
            self._jobs[job.id] = job

        asyncio.create_task(self._run_job(job.id, public_base))
        return job

    async def _run_job(self, job_id: str, public_base: str) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return
        job.status = "running"
        job.message = "转码中"

        try:
            settings = load_settings()
            ffmpeg = resolve_ffmpeg_executable(settings.engines.ffmpeg_path)
            if not Path(ffmpeg).is_file():
                raise RuntimeError("未找到 ffmpeg，请在设置中配置路径")

            src = resolve_media_rel_path(job.source_rel)
            out_path = self._compat_output_path(src)
            out_rel = to_rel_path(out_path)
            if not out_rel:
                raise RuntimeError("无法解析输出相对路径")

            already = await self._probe_already_compat(src, settings.engines.ffmpeg_path)
            if already:
                job.status = "skipped"
                job.message = "已是 H.264+AAC 兼容格式，无需转码"
                job.output_rel = job.source_rel
                job.public_url = build_public_url(
                    to_storage_rel(job.source_rel), public_base
                )
                job.finished_at = datetime.now(timezone.utc).isoformat()
                return

            job.message = "ffmpeg 转码中…"
            await self._run_ffmpeg(ffmpeg, src, out_path, media_type_for_path(src))

            if not out_path.is_file():
                raise RuntimeError("转码完成但未找到输出文件")

            updated = await self._update_playlist_paths(job.source_rel, out_rel)
            job.updated_items = updated
            job.output_rel = out_rel
            job.public_url = build_public_url(to_storage_rel(out_rel), public_base)
            job.status = "completed"
            job.message = f"转码完成，已更新 {updated} 条播放列表引用"
            job.finished_at = datetime.now(timezone.utc).isoformat()
        except Exception as e:
            logger.exception("convert job %s failed", job_id)
            job.status = "failed"
            job.message = str(e)
            job.finished_at = datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _compat_output_path(src: Path) -> Path:
        stem = src.stem
        if stem.endswith("_compat"):
            return src.with_suffix(".mp4")
        return src.with_name(f"{stem}_compat.mp4")

    async def _probe_already_compat(self, src: Path, ffmpeg_path: str) -> bool:
        """Return True if file already looks like h264+aac mp4."""
        if src.suffix.lower() != ".mp4":
            return False
        video_ok, audio_ok = await self._codecs_are_standard(src, ffmpeg_path)
        return video_ok and audio_ok

    async def _codecs_are_standard(self, src: Path, ffmpeg_path: str) -> tuple[bool, bool]:
        ffprobe = resolve_ffprobe_executable(ffmpeg_path)
        if not Path(ffprobe).is_file():
            return False, False
        v_codec = ""
        a_codec = ""
        try:
            v_codec = await self._ffprobe_codec(ffprobe, src, "v:0")
        except Exception:
            v_codec = ""
        try:
            a_codec = await self._ffprobe_codec(ffprobe, src, "a:0")
        except Exception:
            a_codec = ""
        video_ok = v_codec in ("h264", "avc1")
        audio_ok = (not a_codec) or a_codec in ("aac", "mp4a")
        return video_ok, audio_ok

    async def ensure_standard_mp4(self, src: Path) -> Path:
        """Return a progressive H.264+AAC yuv420p MP4.

        Remux when the codecs are already compatible. Re-encode otherwise.
        The incompatible source is removed after a successful replacement.
        """
        if not src.is_file() or media_type_for_path(src) != "video":
            return src
        settings = load_settings()
        ffmpeg = resolve_ffmpeg_executable(settings.engines.ffmpeg_path)
        if not Path(ffmpeg).is_file():
            logger.warning("skip standard mp4, ffmpeg missing: %s", src)
            return src

        video_ok, audio_ok = await self._codecs_are_standard(src, settings.engines.ffmpeg_path)
        if src.suffix.lower() == ".mp4" and video_ok and audio_ok:
            return src

        out, replace_src = self._standard_output_path(src)
        try:
            if video_ok and audio_ok:
                try:
                    await self._remux_mp4(ffmpeg, src, out)
                except Exception:
                    logger.warning("remux failed, re-encode: %s", src)
                    if out.exists() and out.resolve() != src.resolve():
                        out.unlink(missing_ok=True)
                    await self._run_ffmpeg(ffmpeg, src, out, "video")
            else:
                await self._run_ffmpeg(ffmpeg, src, out, "video")
        except Exception:
            logger.exception("standard mp4 failed: %s", src)
            if out.exists() and out.resolve() != src.resolve():
                out.unlink(missing_ok=True)
            return src
        if not out.is_file():
            return src
        if replace_src:
            os.replace(out, src)
            return src
        if out.resolve() != src.resolve():
            try:
                src.unlink()
            except OSError:
                logger.warning("could not remove original %s", src)
        return out

    @staticmethod
    def _standard_output_path(src: Path) -> tuple[Path, bool]:
        if src.suffix.lower() == ".mp4":
            return src.with_name(f".{src.name}.standard-tmp.mp4"), True
        return src.with_suffix(".mp4"), False

    @staticmethod
    async def _remux_mp4(ffmpeg: str, src: Path, out: Path) -> None:
        out.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(src),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(out),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=subprocess_env(),
        )
        _stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = decode_bytes(stderr).strip()
            lines = [ln for ln in err.splitlines() if ln.strip()]
            summary = "\n".join(lines[-12:]) if lines else f"ffmpeg exit {proc.returncode}"
            raise RuntimeError(summary)

    @staticmethod
    async def _ffprobe_codec(ffprobe: str, src: Path, stream_sel: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            stream_sel,
            "-show_entries",
            "stream=codec_name",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(src),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=subprocess_env(),
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(decode_bytes(stderr) or "ffprobe failed")
        return decode_bytes(stdout).strip().split("\n")[0].strip().lower()

    @staticmethod
    async def _run_ffmpeg(ffmpeg: str, src: Path, out: Path, media_type: str = "video") -> None:
        out.parent.mkdir(parents=True, exist_ok=True)
        if media_type == "audio":
            cmd = [
                ffmpeg,
                "-y",
                "-i",
                str(src),
                "-vn",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                str(out),
            ]
        else:
            cmd = [
                ffmpeg,
                "-y",
                "-i",
                str(src),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-profile:v",
                "high",
                "-c:a",
                "aac",
                "-ac",
                "2",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                str(out),
            ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=subprocess_env(),
        )
        _stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = decode_bytes(stderr).strip()
            # last lines are most useful
            lines = [ln for ln in err.splitlines() if ln.strip()]
            summary = "\n".join(lines[-12:]) if lines else f"ffmpeg exit {proc.returncode}"
            raise RuntimeError(summary)

    @staticmethod
    async def _update_playlist_paths(old_rel: str, new_rel: str) -> int:
        async with async_session() as session:
            result = await session.execute(
                update(PlaylistItemORM)
                .where(PlaylistItemORM.rel_path == old_rel)
                .values(rel_path=new_rel)
            )
            await session.commit()
            return int(result.rowcount or 0)


convert_service = FFmpegConvertService()
