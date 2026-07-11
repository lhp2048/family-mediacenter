import asyncio
import re
from pathlib import Path
from typing import Any, Dict, Optional

from app.config import resolve_ytdlp_cookies_file, resolve_ytdlp_executable, settings
from app.engines.base import DownloadEngine, EngineProgress
from app.utils.download_log import (
    append_download_log,
    finalize_download_log,
    init_download_log,
    log_api_path,
    remove_download_log,
)
from app.utils.encoding import decode_bytes, subprocess_env, title_from_task_file


class YtDlpEngine(DownloadEngine):
    name = "ytdlp"
    _processes: Dict[int, asyncio.subprocess.Process] = {}
    _progress: Dict[int, EngineProgress] = {}

    async def is_available(self) -> bool:
        path = resolve_ytdlp_executable(settings.engines.ytdlp_path)
        return Path(path).is_file()

    def _ytdlp_bin(self) -> str:
        return resolve_ytdlp_executable(settings.engines.ytdlp_path)

    def _append_cookies(self, cmd: list[str], options: dict[str, Any]) -> None:
        cookies_file = resolve_ytdlp_cookies_file(options.get("cookies_file"))
        if not cookies_file:
            cookies_file = resolve_ytdlp_cookies_file(settings.engines.ytdlp.cookies_file)
        if cookies_file:
            cmd.extend(["--cookies", cookies_file])
            return
        browser = (
            options.get("cookies_from_browser")
            or settings.engines.ytdlp.cookies_from_browser
            or ""
        ).strip()
        if browser:
            cmd.extend(["--cookies-from-browser", browser])

    def _build_cmd(
        self, url: str, output_dir: str, task_id: int, options: dict[str, Any]
    ) -> list[str]:
        out_template = str(Path(output_dir) / f"task_{task_id}_%(title)s.%(ext)s")
        cmd = [
            self._ytdlp_bin(),
            "--newline",
            "--no-progress",
            "--progress-template",
            "download:%(progress.downloaded_bytes)s|%(progress.total_bytes)s|%(progress.speed)s|%(progress.eta)s",
            "-o",
            out_template,
        ]
        if options.get("audio_only"):
            cmd.extend(["-f", "bestaudio", "--extract-audio", "--audio-format", "mp3"])
        elif options.get("format"):
            cmd.extend(["-f", options["format"]])
        if options.get("subtitle"):
            cmd.extend(["--write-subs", "--write-auto-subs"])
        self._append_cookies(cmd, options)
        cmd.append(url)
        return cmd

    async def start(
        self,
        task_id: int,
        url: str,
        output_dir: str,
        options: dict[str, Any],
    ) -> str:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        cmd = self._build_cmd(url, output_dir, task_id, options)
        init_download_log(task_id, engine=self.name, url=url, cmd=cmd)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=subprocess_env(),
        )
        self._processes[task_id] = proc
        self._progress[task_id] = EngineProgress(status="running")
        asyncio.create_task(self._read_output(task_id, proc, output_dir))
        return str(task_id)

    def _summarize_error(self, output_lines: list[str], returncode: int | None) -> str:
        for line in reversed(output_lines):
            if line.startswith("ERROR:"):
                summary = line
                if "412" in line and "bili" in line.lower():
                    summary += (
                        "。B 站反爬：请在设置 → yt-dlp 配置 Cookie 文件"
                        "（或 cookies_from_browser），并升级 yt-dlp：pip install -U yt-dlp"
                    )
                return summary
        tail = "\n".join(output_lines[-5:]).strip()
        if tail:
            return tail
        return f"yt-dlp exited with code {returncode}"

    async def _read_output(
        self,
        task_id: int,
        proc: asyncio.subprocess.Process,
        output_dir: str,
    ) -> None:
        prog = self._progress.get(task_id, EngineProgress())
        output_lines: list[str] = []
        if proc.stdout:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                text = decode_bytes(line).strip()
                output_lines.append(text)
                append_download_log(task_id, text)
                if text.startswith("download:"):
                    self._parse_progress_line(task_id, text)
                if "[download] Destination:" in text:
                    path_part = text.split("Destination:", 1)[1].strip()
                    prog.file_path = path_part
                if "[Merger] Merging formats into" in text:
                    path_part = text.split("into", 1)[1].strip().strip('"')
                    prog.file_path = path_part
                if text.startswith("[download]") and "has already been downloaded" in text:
                    match = re.search(r"\[download\]\s+(.+?)\s+has already", text)
                    if match:
                        prog.file_path = match.group(1).strip()

        await proc.wait()
        prog = self._progress.get(task_id, EngineProgress())
        if proc.returncode == 0:
            prog.status = "completed"
            prog.progress = 100.0
            latest = self._find_latest_file(output_dir, task_id)
            if latest:
                prog.file_path = latest
            elif prog.file_path and not Path(prog.file_path).exists():
                prog.file_path = ""
            if prog.file_path:
                p = Path(prog.file_path)
                if p.exists():
                    prog.file_size = p.stat().st_size
                    prog.title = title_from_task_file(prog.file_path, task_id)
            remove_download_log(task_id)
        else:
            prog.status = "failed"
            finalize_download_log(task_id, return_code=proc.returncode)
            summary = self._summarize_error(output_lines, proc.returncode)
            prog.error_message = f"{summary}（完整日志: {log_api_path(task_id)}）"
        self._progress[task_id] = prog
        self._processes.pop(task_id, None)

    def _parse_progress_line(self, task_id: int, line: str) -> None:
        parts = line.replace("download:", "").split("|")
        if len(parts) < 3:
            return
        prog = self._progress.get(task_id, EngineProgress())
        try:
            downloaded = int(parts[0]) if parts[0] else 0
            total = int(parts[1]) if parts[1] and parts[1] != "None" else 0
            speed_raw = parts[2]
            if total > 0:
                prog.progress = min(100.0, downloaded / total * 100.0)
            prog.speed = speed_raw if speed_raw and speed_raw != "None" else ""
        except (ValueError, TypeError):
            pass
        self._progress[task_id] = prog

    def _find_latest_file(self, output_dir: str, task_id: int) -> str:
        base = Path(output_dir)
        candidates = list(base.glob(f"task_{task_id}_*"))
        if not candidates:
            return ""
        latest = max(candidates, key=lambda p: p.stat().st_mtime)
        return str(latest)

    async def poll(self, engine_task_id: str, task_id: int) -> EngineProgress:
        return self._progress.get(task_id, EngineProgress(status="running"))

    async def pause(self, engine_task_id: str, task_id: int) -> bool:
        proc = self._processes.get(task_id)
        if proc and proc.returncode is None:
            proc.terminate()
            prog = self._progress.get(task_id, EngineProgress())
            prog.status = "paused"
            self._progress[task_id] = prog
            return True
        return False

    async def cancel(self, engine_task_id: str, task_id: int) -> bool:
        proc = self._processes.get(task_id)
        if proc and proc.returncode is None:
            proc.kill()
        prog = self._progress.get(task_id, EngineProgress())
        prog.status = "cancelled"
        self._progress[task_id] = prog
        self._processes.pop(task_id, None)
        return True
