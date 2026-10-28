"""Engine install / update / process lifecycle (yt-dlp, ffmpeg, aria2, alist)."""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import signal
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from app.config import PROJECT_ROOT, load_settings, resolve_ffmpeg_executable, resolve_ytdlp_executable
from app.services.engine_status import get_engine_status, normalize_runtime
from app.utils.encoding import decode_bytes, subprocess_env

logger = logging.getLogger(__name__)

ACTIONS_YTDLP_FFMPEG = frozenset({"install", "check_update", "update", "restart"})
ACTIONS_PROCESS = frozenset({"start", "stop", "restart", "check_update"})
ACTIONS_ALIST = ACTIONS_PROCESS | frozenset({"set_admin_password"})
ALLOWED: dict[str, frozenset[str]] = {
    "ytdlp": ACTIONS_YTDLP_FFMPEG,
    "ffmpeg": ACTIONS_YTDLP_FFMPEG,
    "aria2": ACTIONS_PROCESS,
    "alist": ACTIONS_ALIST,
}
PROCESS_CONTROL_ACTIONS = frozenset({"start", "stop", "restart"})
RUNTIME_LABEL = {"local": "本地进程", "docker": "Docker", "remote": "远程"}


@dataclass
class LifecycleJob:
    id: str
    engine: str
    action: str
    status: str = "pending"  # pending|running|completed|failed
    message: str = ""
    detail: str = ""
    local_version: str = ""
    remote_version: str = ""
    password: str = ""  # ephemeral; never exposed in to_dict
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "engine": self.engine,
            "action": self.action,
            "status": self.status,
            "message": self.message,
            "detail": self.detail,
            "local_version": self.local_version,
            "remote_version": self.remote_version,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "ok": self.status == "completed",
        }


def _finish(job: LifecycleJob, status: str, message: str, detail: str = "") -> None:
    job.status = status
    job.message = message
    if detail:
        job.detail = detail
    job.finished_at = datetime.now(timezone.utc).isoformat()


def _stderr_summary(text: str, limit: int = 12) -> str:
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    return "\n".join(lines[-limit:]) if lines else ""


async def _run_cmd(
    cmd: list[str],
    *,
    cwd: Optional[Path] = None,
    timeout: float = 300.0,
) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(cwd) if cwd else None,
        env=subprocess_env(),
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return 124, "", f"命令超时 ({timeout:.0f}s): {' '.join(cmd)}"
    return (
        proc.returncode or 0,
        decode_bytes(stdout_b),
        decode_bytes(stderr_b),
    )


def _venv_python() -> Path:
    if sys.platform == "win32":
        return PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    return PROJECT_ROOT / ".venv" / "bin" / "python"


def _ensure_venv_python() -> Path:
    py = _venv_python()
    if py.is_file():
        return py
    raise RuntimeError(
        f"未找到项目虚拟环境 Python：{py}\n"
        "请先运行 ./scripts/setup_venv.sh 或 scripts\\setup_venv.bat"
    )


def _which(name: str) -> Optional[str]:
    return shutil.which(name)


def _parse_url_port(url: str, default: int) -> int:
    try:
        raw = (url or "").strip()
        parsed = urlparse(raw if "://" in raw else f"http://{raw}")
        if parsed.port:
            return int(parsed.port)
    except Exception:
        pass
    return default


def _parse_rpc_port(rpc_url: str) -> int:
    return _parse_url_port(rpc_url, 6800)


def resolve_aria2c() -> Optional[str]:
    found = _which("aria2c")
    if found:
        return found
    for candidate in (
        "/opt/homebrew/bin/aria2c",
        "/usr/local/bin/aria2c",
        str(PROJECT_ROOT / ".venv" / "bin" / "aria2c"),
    ):
        if Path(candidate).is_file():
            return candidate
    return None


def resolve_alist_binary(binary_path: str = "") -> Optional[str]:
    bp = (binary_path or "").strip()
    if bp and Path(bp).is_file():
        return bp
    found = _which("alist")
    if found:
        return found
    for candidate in (
        "/opt/homebrew/bin/alist",
        "/usr/local/bin/alist",
        str(PROJECT_ROOT / "bin" / "alist"),
        str(PROJECT_ROOT / "data" / "alist" / "alist"),
        str(Path.home() / "alist" / "alist"),
    ):
        if Path(candidate).is_file():
            return candidate
    return None


def _aria2_runtime() -> str:
    return normalize_runtime(load_settings().engines.aria2.runtime)


def _alist_runtime() -> str:
    return normalize_runtime(load_settings().engines.alist.runtime)


class EngineLifecycleService:
    def __init__(self) -> None:
        self._jobs: dict[str, LifecycleJob] = {}
        self._lock = asyncio.Lock()

    def get_job(self, job_id: str) -> Optional[LifecycleJob]:
        return self._jobs.get(job_id)

    def validate(self, engine: str, action: str) -> None:
        eng = (engine or "").lower().strip()
        act = (action or "").lower().strip()
        if eng not in ALLOWED:
            raise ValueError(f"不支持的引擎生命周期操作: {engine}")
        if act not in ALLOWED[eng]:
            raise ValueError(f"引擎 {eng} 不支持动作 {action}")
        if eng in ("aria2", "alist") and act in PROCESS_CONTROL_ACTIONS:
            runtime = _aria2_runtime() if eng == "aria2" else _alist_runtime()
            if runtime == "remote":
                raise ValueError(
                    f"{eng} 当前为远程模式，无法在本机启停；请在设置中改为本地进程或 Docker"
                )
        if eng == "alist" and act == "set_admin_password":
            if _alist_runtime() != "local":
                raise ValueError("设置管理员密码仅支持「本地进程」模式")

    async def start_action(
        self, engine: str, action: str, *, password: str = ""
    ) -> LifecycleJob:
        eng = engine.lower().strip()
        act = action.lower().strip()
        self.validate(eng, act)
        if act == "set_admin_password" and not (password or "").strip():
            raise ValueError("请提供新的管理员密码")

        async with self._lock:
            for job in self._jobs.values():
                if (
                    job.engine == eng
                    and job.action == act
                    and job.status in ("pending", "running")
                ):
                    return job

            job = LifecycleJob(
                id=uuid.uuid4().hex[:12],
                engine=eng,
                action=act,
                status="pending",
                message="排队中",
                password=(password or "").strip(),
            )
            self._jobs[job.id] = job

        asyncio.create_task(self._run(job.id))
        return job

    async def _run(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return
        job.status = "running"
        job.message = "执行中"
        try:
            if job.engine == "ytdlp":
                await self._handle_ytdlp(job)
            elif job.engine == "ffmpeg":
                await self._handle_ffmpeg(job)
            elif job.engine == "aria2":
                await self._handle_aria2(job)
            elif job.engine == "alist":
                await self._handle_alist(job)
            else:
                raise ValueError(f"未知引擎: {job.engine}")
        except Exception as e:
            logger.exception("lifecycle %s %s failed", job.engine, job.action)
            _finish(job, "failed", str(e), detail=str(e))

    # ---- yt-dlp ----

    async def _handle_ytdlp(self, job: LifecycleJob) -> None:
        if job.action == "restart":
            info = await get_engine_status("ytdlp")
            job.local_version = (info.version if info else "") or ""
            if info and info.available:
                _finish(job, "completed", f"状态已刷新：{info.message}")
            else:
                _finish(
                    job,
                    "completed",
                    f"状态已刷新：{(info.message if info else '不可用')}",
                )
            return

        if job.action == "check_update":
            local = await self._ytdlp_local_version()
            job.local_version = local
            remote = await self._ytdlp_pypi_version()
            job.remote_version = remote or ""
            if not local:
                _finish(job, "completed", "未安装 yt-dlp，可点击「安装」")
                return
            if not remote:
                _finish(job, "completed", f"本地 {local}；无法检查远程版本")
                return
            if local == remote or local.lstrip("v") == remote.lstrip("v"):
                _finish(job, "completed", f"已是最新：{local}")
            else:
                _finish(job, "completed", f"有更新：本地 {local} → 远程 {remote}")
            return

        # install / update
        py = _ensure_venv_python()
        job.message = "pip 安装 yt-dlp…" if job.action == "install" else "pip 升级 yt-dlp…"
        code, out, err = await _run_cmd(
            [str(py), "-m", "pip", "install", "-U", "yt-dlp"],
            cwd=PROJECT_ROOT,
            timeout=600.0,
        )
        if code != 0:
            _finish(
                job,
                "failed",
                "pip 安装/升级 yt-dlp 失败",
                detail=_stderr_summary(err or out),
            )
            return
        local = await self._ytdlp_local_version()
        job.local_version = local
        _finish(job, "completed", f"yt-dlp 已就绪：{local or 'ok'}", detail=_stderr_summary(out))

    async def _ytdlp_local_version(self) -> str:
        settings = load_settings()
        exe = resolve_ytdlp_executable(settings.engines.ytdlp_path)
        if not exe or not Path(exe).is_file():
            return ""
        code, out, err = await _run_cmd([exe, "--version"], timeout=30.0)
        if code != 0:
            return ""
        return (out or err).strip().split("\n")[0].strip()

    async def _ytdlp_pypi_version(self) -> str:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                r = await client.get("https://pypi.org/pypi/yt-dlp/json")
                r.raise_for_status()
                return str(r.json().get("info", {}).get("version", "")).strip()
        except Exception:
            return ""

    # ---- ffmpeg ----

    async def _handle_ffmpeg(self, job: LifecycleJob) -> None:
        if job.action == "restart":
            info = await get_engine_status("ffmpeg")
            job.local_version = (info.version if info else "") or ""
            _finish(
                job,
                "completed",
                f"状态已刷新：{(info.message if info else '不可用')}",
            )
            return

        brew = _which("brew")
        scoop = _which("scoop")

        if job.action == "check_update":
            local = await self._ffmpeg_local_version()
            job.local_version = local
            if brew:
                code, out, err = await _run_cmd(
                    [brew, "outdated", "--quiet", "ffmpeg"], timeout=60.0
                )
                text = (out or err).strip()
                if code == 0 and "ffmpeg" in text:
                    _finish(job, "completed", f"有更新（brew）：本地 {local or '?'}")
                else:
                    _finish(job, "completed", f"brew 显示已最新或未托管：{local or '未安装'}")
                return
            if scoop:
                code, out, err = await _run_cmd([scoop, "status", "ffmpeg"], timeout=60.0)
                text = (out or err).lower()
                if "update" in text or "outdated" in text:
                    _finish(job, "completed", f"scoop 可能有更新：{local or '?'}")
                else:
                    _finish(job, "completed", f"本地 {local or '未安装'}（scoop 未报更新）")
                return
            if local:
                _finish(job, "completed", f"本地 {local}；无 brew/scoop，无法自动检查更新")
            else:
                _finish(job, "completed", "未安装 ffmpeg")
            return

        # install / update
        if brew:
            sub = "install" if job.action == "install" else "upgrade"
            job.message = f"brew {sub} ffmpeg…"
            code, out, err = await _run_cmd([brew, sub, "ffmpeg"], timeout=900.0)
            if code != 0:
                summary = _stderr_summary(err or out)
                local = await self._ffmpeg_local_version()
                if local and job.action == "install":
                    _finish(job, "completed", f"ffmpeg 已存在：{local}", detail=summary)
                    job.local_version = local
                    return
                # brew upgrade when already latest often exits 1
                if local and job.action == "update" and "already installed" in (err or out).lower():
                    job.local_version = local
                    _finish(job, "completed", f"ffmpeg 已是最新：{local}", detail=summary)
                    return
                _finish(job, "failed", f"brew {sub} ffmpeg 失败", detail=summary)
                return
            local = await self._ffmpeg_local_version()
            job.local_version = local
            _finish(job, "completed", f"ffmpeg 已就绪：{local or 'ok'}")
            return

        if scoop:
            if job.action == "install":
                cmd = [scoop, "install", "ffmpeg"]
            else:
                cmd = [scoop, "update", "ffmpeg"]
            job.message = " ".join(cmd)
            code, out, err = await _run_cmd(cmd, timeout=900.0)
            if code != 0:
                local = await self._ffmpeg_local_version()
                if local and job.action == "install":
                    job.local_version = local
                    _finish(job, "completed", f"ffmpeg 已存在：{local}", detail=_stderr_summary(err or out))
                    return
                _finish(job, "failed", "scoop 安装/更新 ffmpeg 失败", detail=_stderr_summary(err or out))
                return
            local = await self._ffmpeg_local_version()
            job.local_version = local
            _finish(job, "completed", f"ffmpeg 已就绪：{local or 'ok'}")
            return

        help_text = (
            "未检测到 brew / scoop，无法自动安装 ffmpeg。\n"
            "macOS: brew install ffmpeg\n"
            "Windows: scoop install ffmpeg\n"
            "官网: https://ffmpeg.org/download.html"
        )
        _finish(job, "failed", "无法自动安装 ffmpeg", detail=help_text)

    async def _ffmpeg_local_version(self) -> str:
        settings = load_settings()
        exe = resolve_ffmpeg_executable(settings.engines.ffmpeg_path)
        if not exe or not Path(exe).is_file():
            return ""
        code, out, err = await _run_cmd([exe, "-version"], timeout=30.0)
        text = (out or err).strip().split("\n")[0]
        # ffmpeg version n6.1 Copyright...
        m = re.search(r"ffmpeg version\s+(\S+)", text, re.I)
        return m.group(1) if m else text[:40]

    # ---- docker helpers ----

    async def _docker_ctl(self, container: str, action: str) -> tuple[int, str, str]:
        docker = _which("docker")
        if not docker:
            return 127, "", "未找到 docker 命令（请安装 Docker 或改用本地进程模式）"
        name = (container or "").strip()
        if not name:
            return 1, "", "未配置 container_name"
        return await _run_cmd([docker, action, name], timeout=90.0)

    # ---- aria2 ----

    async def _handle_aria2(self, job: LifecycleJob) -> None:
        runtime = _aria2_runtime()
        if job.action == "check_update":
            path = resolve_aria2c()
            if not path:
                _finish(
                    job,
                    "completed",
                    f"模式={RUNTIME_LABEL.get(runtime, runtime)}；未找到 aria2c（本期不提供自动安装）",
                )
                return
            code, out, err = await _run_cmd([path, "-v"], timeout=20.0)
            ver_line = (out or err).strip().split("\n")[0]
            job.local_version = ver_line[:80]
            _finish(
                job,
                "completed",
                f"[{RUNTIME_LABEL.get(runtime, runtime)}] 本地：{ver_line[:80]}（不支持自动更新）",
            )
            return

        if runtime == "docker":
            await self._handle_docker_engine(job, "aria2")
            return

        if job.action == "stop":
            n = await self._aria2_stop()
            if n == 0:
                _finish(job, "completed", "未找到匹配的本机 aria2 RPC 进程")
            else:
                _finish(job, "completed", f"已停止 {n} 个 aria2c 进程")
            return

        if job.action == "start":
            await self._aria2_start(job)
            return

        # restart
        await self._aria2_stop()
        await asyncio.sleep(0.4)
        await self._aria2_start(job)

    async def _handle_docker_engine(self, job: LifecycleJob, engine: str) -> None:
        settings = load_settings()
        if engine == "aria2":
            container = settings.engines.aria2.container_name or "family-mediacenter-aria2"
            ready = self._aria2_rpc_ok
        else:
            container = settings.engines.alist.container_name or "family-mediacenter-alist"
            ready = self._alist_http_ok

        docker_action = {"start": "start", "stop": "stop", "restart": "restart"}.get(job.action)
        if not docker_action:
            _finish(job, "failed", f"Docker 模式不支持 {job.action}")
            return

        code, out, err = await self._docker_ctl(container, docker_action)
        if code != 0:
            _finish(
                job,
                "failed",
                f"docker {docker_action} {container} 失败",
                detail=_stderr_summary(err or out),
            )
            return

        if job.action == "stop":
            _finish(job, "completed", f"已 docker stop {container}")
            return

        for _ in range(24):
            await asyncio.sleep(0.25)
            if await ready():
                _finish(job, "completed", f"已 docker {docker_action} {container}，服务就绪")
                return
        _finish(
            job,
            "failed",
            f"容器已 {docker_action}，但服务尚未就绪",
            detail=f"请检查容器 {container} 日志与端口配置",
        )

    async def _aria2_rpc_ok(self) -> bool:
        info = await get_engine_status("aria2")
        return bool(info and info.available)

    async def _alist_http_ok(self) -> bool:
        """Probe Alist HTTP even if engine not enabled in settings."""
        settings = load_settings()
        url = (settings.engines.alist.url or "").rstrip("/")
        if not url:
            return False
        paths = ("/api/public/settings", "/ping", "/")
        try:
            async with httpx.AsyncClient(
                timeout=5.0, follow_redirects=True, trust_env=False
            ) as client:
                for path in paths:
                    try:
                        r = await client.get(f"{url}{path}")
                        if r.status_code >= 500:
                            continue
                        if path == "/api/public/settings":
                            try:
                                body = r.json()
                                if body.get("code") == 200:
                                    return True
                            except Exception:
                                pass
                            continue
                        if r.status_code < 500:
                            return True
                    except Exception:
                        continue
        except Exception:
            return False
        return False

    async def _aria2_start(self, job: LifecycleJob) -> None:
        if await self._aria2_rpc_ok():
            _finish(job, "completed", "aria2 RPC 已在运行")
            return
        path = resolve_aria2c()
        if not path:
            _finish(
                job,
                "failed",
                "未找到 aria2c",
                detail="请安装：brew install aria2 或 scoop install aria2",
            )
            return
        settings = load_settings()
        port = _parse_rpc_port(settings.engines.aria2.rpc_url)
        secret = (settings.engines.aria2.secret or "").strip()
        cmd = [
            path,
            "--enable-rpc",
            "--rpc-listen-all=false",
            f"--rpc-listen-port={port}",
        ]
        if secret:
            cmd.append(f"--rpc-secret={secret}")

        # Detach: don't wait for process end
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                env=subprocess_env(),
                start_new_session=True,
            )
        except Exception as e:
            _finish(job, "failed", f"启动 aria2c 失败: {e}")
            return

        # Wait briefly for RPC
        for _ in range(20):
            await asyncio.sleep(0.25)
            if await self._aria2_rpc_ok():
                _finish(job, "completed", f"aria2c 已启动 (pid≈{proc.pid}, port={port})")
                return
        _finish(
            job,
            "failed",
            "已拉起 aria2c 但 RPC 尚未就绪",
            detail=f"请检查端口 {port} 与 secret 配置",
        )

    async def _aria2_stop(self) -> int:
        settings = load_settings()
        port = _parse_rpc_port(settings.engines.aria2.rpc_url)
        pids = await self._find_aria2_pids(port)
        return await self._kill_pids(pids)

    # ---- alist ----

    async def _handle_alist(self, job: LifecycleJob) -> None:
        runtime = _alist_runtime()
        settings = load_settings()
        if job.action == "set_admin_password":
            await self._alist_set_admin_password(job)
            return
        if job.action == "check_update":
            path = resolve_alist_binary(settings.engines.alist.binary_path)
            if not path:
                _finish(
                    job,
                    "completed",
                    f"模式={RUNTIME_LABEL.get(runtime, runtime)}；未找到 alist 二进制",
                )
                return
            code, out, err = await _run_cmd([path, "version"], timeout=20.0)
            ver_line = (out or err).strip().split("\n")[0]
            if not ver_line:
                code, out, err = await _run_cmd([path, "--version"], timeout=20.0)
                ver_line = (out or err).strip().split("\n")[0]
            job.local_version = ver_line[:80]
            _finish(
                job,
                "completed",
                f"[{RUNTIME_LABEL.get(runtime, runtime)}] {ver_line[:80] or path}",
            )
            return

        if runtime == "docker":
            await self._handle_docker_engine(job, "alist")
            return

        if job.action == "stop":
            n = await self._alist_stop()
            if n == 0:
                _finish(job, "completed", "未找到匹配的本机 alist 进程")
            else:
                _finish(job, "completed", f"已停止 {n} 个 alist 进程")
            return

        if job.action == "start":
            await self._alist_start(job)
            return

        await self._alist_stop()
        await asyncio.sleep(0.4)
        await self._alist_start(job)

    def _alist_data_dir(self) -> Path:
        data_dir = PROJECT_ROOT / "data" / "alist"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir

    async def _alist_set_admin_password(self, job: LifecycleJob) -> None:
        password = (job.password or "").strip()
        job.password = ""  # wipe ASAP
        if not password:
            _finish(job, "failed", "密码不能为空")
            return
        if len(password) < 4:
            _finish(job, "failed", "密码至少 4 位")
            return
        settings = load_settings()
        path = resolve_alist_binary(settings.engines.alist.binary_path)
        if not path:
            _finish(
                job,
                "failed",
                "未找到 alist 二进制",
                detail="请在设置中填写 binary_path",
            )
            return
        data_dir = self._alist_data_dir()
        code, out, err = await _run_cmd(
            [path, "admin", "--data", str(data_dir), "set", password],
            timeout=60.0,
            cwd=str(data_dir),
        )
        text = (out or "") + "\n" + (err or "")
        if code != 0:
            # older CLI: alist admin set PASSWORD (cwd/data)
            code2, out2, err2 = await _run_cmd(
                [path, "admin", "set", password],
                timeout=60.0,
                cwd=str(data_dir),
            )
            text2 = (out2 or "") + "\n" + (err2 or "")
            if code2 != 0:
                _finish(
                    job,
                    "failed",
                    "设置管理员密码失败",
                    detail=_stderr_summary(text + "\n" + text2),
                )
                return
            text = text2
        _finish(
            job,
            "completed",
            "已设置 admin 密码（作用于 Media Center 的 data/alist）",
            detail=(
                "请在组件页重启 Alist，然后用 admin + 新密码登录后台，"
                "重新获取 Token 填回设置。\n"
                f"data={data_dir}"
            ),
        )

    async def _alist_start(self, job: LifecycleJob) -> None:
        if await self._alist_http_ok():
            _finish(job, "completed", "Alist 已在运行")
            return
        settings = load_settings()
        path = resolve_alist_binary(settings.engines.alist.binary_path)
        if not path:
            _finish(
                job,
                "failed",
                "未找到 alist 二进制",
                detail="请安装 Alist/OpenList（darwin-amd64 / arm64），或在设置中填写 binary_path",
            )
            return

        # Sanity-check binary before detach (catches wrong arch early)
        code, out, err = await _run_cmd([path, "version"], timeout=15.0)
        if code != 0:
            code2, out2, err2 = await _run_cmd([path, "--version"], timeout=15.0)
            if code2 != 0:
                _finish(
                    job,
                    "failed",
                    "alist 二进制无法执行",
                    detail=_stderr_summary(err or out or err2 or out2)
                    or f"path={path}（Intel Mac 请用 alist-darwin-amd64）",
                )
                return

        port = _parse_url_port(settings.engines.alist.url, 5244)
        data_dir = self._alist_data_dir()
        log_path = data_dir / "server.log"
        cmd = [path, "server", "--data", str(data_dir)]
        try:
            log_f = open(log_path, "ab", buffering=0)
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=log_f,
                stderr=log_f,
                env=subprocess_env(),
                start_new_session=True,
                cwd=str(data_dir),
            )
        except Exception as e:
            _finish(job, "failed", f"启动 alist 失败: {e}")
            return

        # First boot can take longer (init db / config)
        for _ in range(60):
            await asyncio.sleep(0.5)
            if proc.returncode is not None:
                tail = ""
                try:
                    tail = log_path.read_text(encoding="utf-8", errors="replace")[-1200:]
                except OSError:
                    pass
                _finish(
                    job,
                    "failed",
                    f"alist 进程已退出 (code={proc.returncode})",
                    detail=tail or f"日志：{log_path}",
                )
                return
            if await self._alist_http_ok():
                _finish(
                    job,
                    "completed",
                    f"alist 已启动 (pid≈{proc.pid}, url={settings.engines.alist.url or port})",
                )
                return

        alive = proc.returncode is None
        tail = ""
        try:
            tail = log_path.read_text(encoding="utf-8", errors="replace")[-1200:]
        except OSError:
            pass
        _finish(
            job,
            "failed",
            "已拉起 alist 但 HTTP 尚未就绪",
            detail=(
                f"url={settings.engines.alist.url} binary={path} "
                f"alive={alive} log={log_path}\n"
                f"{tail or '（日志为空：可能端口被占用或配置端口与 URL 不一致）'}"
            ),
        )

    async def _alist_stop(self) -> int:
        pids = await self._find_pids_by_name("alist", 0, self._cmdline_matches_alist)
        return await self._kill_pids(pids)

    @staticmethod
    def _cmdline_matches_alist(cmdline: str, _port: int) -> bool:
        c = cmdline.lower()
        if "alist" not in c:
            return False
        tokens = c.replace("\\", "/").split()
        base = Path(tokens[0]).name if tokens else ""
        if base in ("alist", "alist.exe") and ("server" in tokens or len(tokens) == 1):
            return True
        return base in ("alist", "alist.exe") and "server" in c

    async def _find_pids_by_name(self, name: str, port: int, matcher) -> list[int]:
        pids: list[int] = []
        if sys.platform == "win32":
            exe = f"{name}.exe"
            code, out, _ = await _run_cmd(
                [
                    "wmic",
                    "process",
                    "where",
                    f"name='{exe}'",
                    "get",
                    "ProcessId,CommandLine",
                    "/FORMAT:LIST",
                ],
                timeout=20.0,
            )
            if code != 0:
                return pids
            cur_pid: Optional[int] = None
            for line in out.splitlines():
                line = line.strip()
                if line.lower().startswith("processid="):
                    try:
                        cur_pid = int(line.split("=", 1)[1].strip())
                    except ValueError:
                        cur_pid = None
                elif line.lower().startswith("commandline="):
                    cur_cmd = line.split("=", 1)[1]
                    if cur_pid and matcher(cur_cmd, port):
                        pids.append(cur_pid)
                    cur_pid = None
            return pids

        code, out, _ = await _run_cmd(["ps", "-ax", "-o", "pid=,command="], timeout=15.0)
        if code != 0:
            return []
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(None, 1)
            if len(parts) < 2:
                continue
            try:
                pid = int(parts[0])
            except ValueError:
                continue
            cmd = parts[1]
            if name not in cmd:
                continue
            if matcher(cmd, port):
                pids.append(pid)
        return pids

    async def _kill_pids(self, pids: list[int]) -> int:
        killed = 0
        for pid in pids:
            try:
                if sys.platform == "win32":
                    await _run_cmd(["taskkill", "/PID", str(pid), "/F"], timeout=15.0)
                else:
                    os.kill(pid, signal.SIGTERM)
                killed += 1
            except ProcessLookupError:
                pass
            except Exception as e:
                logger.warning("kill pid %s: %s", pid, e)
        if killed and sys.platform != "win32":
            await asyncio.sleep(0.3)
            for pid in pids:
                try:
                    os.kill(pid, 0)
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except Exception:
                    pass
        return killed

    async def _find_aria2_pids(self, port: int) -> list[int]:
        """Find aria2c PIDs that look like our RPC instance."""
        return await self._find_pids_by_name("aria2c", port, self._cmdline_matches_rpc)

    @staticmethod
    def _cmdline_matches_rpc(cmdline: str, port: int) -> bool:
        c = cmdline.lower()
        if "enable-rpc" not in c and "--enable-rpc" not in c:
            return False
        # port match if present; if no port flag, still accept enable-rpc aria2c
        if f"rpc-listen-port={port}" in c or f"rpc-listen-port {port}" in c:
            return True
        if "rpc-listen-port" not in c and port == 6800:
            return True
        return "rpc-listen-port" not in c


lifecycle_service = EngineLifecycleService()
