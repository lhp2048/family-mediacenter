import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import httpx

from app.config import load_settings, resolve_download_dir, resolve_ffmpeg_executable, resolve_ytdlp_executable
from app.utils.encoding import decode_bytes, subprocess_env


@dataclass
class EngineStatusInfo:
    name: str
    display_name: str
    description: str
    available: bool
    enabled: bool
    version: str = ""
    endpoint: str = ""
    message: str = ""
    supports: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    active_tasks: int = 0
    runtime: str = ""  # local | docker | remote (process engines)
    process_control: bool = False  # show start/stop/restart


def normalize_runtime(value: str | None) -> str:
    v = (value or "local").strip().lower()
    if v in ("local", "docker", "remote"):
        return v
    return "local"


async def _run_version_cmd(cmd: list[str]) -> str:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=subprocess_env(),
    )
    stdout, _ = await proc.communicate()
    text = decode_bytes(stdout).strip()
    if proc.returncode != 0:
        raise RuntimeError(text or f"exit code {proc.returncode}")
    return text.split("\n")[0].strip()


async def get_ytdlp_status(settings=None) -> EngineStatusInfo:
    s = settings or load_settings()
    path_cfg = s.engines.ytdlp_path
    resolved = resolve_ytdlp_executable(path_cfg)

    info = EngineStatusInfo(
        name="ytdlp",
        display_name="yt-dlp",
        description="音视频下载（YouTube、Bilibili、Twitter 等）",
        available=False,
        enabled=True,
        endpoint=resolved or path_cfg,
        supports=["音视频站点", "播客", "直播回放"],
        config={"ytdlp_path": path_cfg},
    )

    if not resolved or not Path(resolved).is_file():
        info.message = "未找到 yt-dlp，请安装或配置正确路径"
        return info

    try:
        info.version = await _run_version_cmd([resolved, "--version"])
        info.available = True
        info.message = "运行正常"
    except Exception as e:
        info.message = str(e)

    return info


async def get_aria2_status(settings=None) -> EngineStatusInfo:
    s = settings or load_settings()
    aria_cfg = s.engines.aria2
    runtime = normalize_runtime(getattr(aria_cfg, "runtime", None))
    info = EngineStatusInfo(
        name="aria2",
        display_name="aria2",
        description="HTTP/HTTPS 直链、磁力链接、BT 下载",
        available=False,
        enabled=True,
        endpoint=aria_cfg.rpc_url,
        supports=["HTTP/HTTPS", "磁力链接", "BT"],
        runtime=runtime,
        process_control=runtime in ("local", "docker"),
        config={
            "rpc_url": aria_cfg.rpc_url,
            "secret": "***" if aria_cfg.secret else "",
            "runtime": runtime,
            "container_name": getattr(aria_cfg, "container_name", "") or "",
        },
    )

    try:
        from app.engines.aria2 import Aria2Engine

        engine = Aria2Engine()
        client = engine._client()
        version = client.client.get_version()
        info.version = str(version.get("version", version) if isinstance(version, dict) else version)
        downloads = client.get_downloads()
        info.active_tasks = sum(1 for d in downloads if d.is_active)
        info.available = True
        info.message = f"RPC 连接正常，活跃任务 {info.active_tasks} 个"
    except Exception as e:
        info.message = f"无法连接 aria2 RPC: {e}"

    return info


async def get_alist_status(settings=None) -> EngineStatusInfo:
    s = settings or load_settings()
    alist_cfg = s.engines.alist
    runtime = normalize_runtime(getattr(alist_cfg, "runtime", None))
    info = EngineStatusInfo(
        name="alist",
        display_name="Alist / OpenList",
        description="网盘统一接入、分享链接解析与离线下载",
        available=False,
        enabled=alist_cfg.enabled,
        endpoint=alist_cfg.url,
        supports=["网盘分享链接", "Alist 路径", "离线下载到网盘"],
        runtime=runtime,
        process_control=runtime in ("local", "docker"),
        config={
            "enabled": alist_cfg.enabled,
            "url": alist_cfg.url,
            "token": "***" if alist_cfg.token else "",
            "runtime": runtime,
            "container_name": getattr(alist_cfg, "container_name", "") or "",
            "binary_path": getattr(alist_cfg, "binary_path", "") or "",
        },
    )

    if not alist_cfg.enabled:
        info.message = "未启用，请在设置中开启"
        return info

    if not alist_cfg.url:
        info.message = "未配置服务地址"
        return info

    try:
        base = alist_cfg.url.rstrip("/")
        async with httpx.AsyncClient(
            timeout=10.0, follow_redirects=True, trust_env=False
        ) as client:
            r = await client.get(f"{base}/api/public/settings")
            if r.status_code == 502:
                info.message = (
                    "502 Bad Gateway：端口有响应但 Alist 后端未就绪。"
                    "请确认本机 alist 进程在跑，或检查反向代理是否指向正确端口"
                )
                return info
            if r.status_code == 503:
                info.message = "503：Alist 暂时不可用，请稍后重试或查看 alist 日志"
                return info
            r.raise_for_status()
            body = r.json()
            if body.get("code") == 200:
                data = body.get("data", {})
                info.version = str(data.get("version", ""))
                info.available = True
                info.message = "服务连接正常"
            else:
                info.message = body.get("message", "Alist API 返回异常")
    except httpx.HTTPStatusError as e:
        code = e.response.status_code if e.response is not None else "?"
        info.message = f"无法连接 Alist：HTTP {code}（请确认 {alist_cfg.url} 是 Alist 服务）"
    except Exception as e:
        info.message = f"无法连接 Alist: {e}"

    return info


async def get_ffmpeg_status(settings=None) -> EngineStatusInfo:
    s = settings or load_settings()
    path_cfg = s.engines.ffmpeg_path
    resolved = resolve_ffmpeg_executable(path_cfg)

    info = EngineStatusInfo(
        name="ffmpeg",
        display_name="ffmpeg",
        description="音视频转码（H.264/AAC 兼容格式，供 iPad 等设备播放）",
        available=False,
        enabled=True,
        endpoint=resolved or path_cfg,
        supports=["H.264 转码", "AAC", "兼容 mp4"],
        config={"ffmpeg_path": path_cfg},
    )

    if not resolved or not Path(resolved).is_file():
        info.message = "未找到 ffmpeg，请安装或配置正确路径"
        return info

    try:
        text = await _run_version_cmd([resolved, "-version"])
        # "ffmpeg version n6.1 ..."
        info.version = text.replace("ffmpeg version ", "").split(" ")[0]
        info.available = True
        info.message = "运行正常"
        info.endpoint = resolved
    except Exception as e:
        info.message = str(e)

    return info


async def get_all_engine_status() -> list[EngineStatusInfo]:
    s = load_settings()
    results = await asyncio.gather(
        get_ytdlp_status(s),
        get_aria2_status(s),
        get_alist_status(s),
        get_ffmpeg_status(s),
    )
    return list(results)


async def get_engine_status(name: str) -> Optional[EngineStatusInfo]:
    mapping = {
        "ytdlp": get_ytdlp_status,
        "aria2": get_aria2_status,
        "alist": get_alist_status,
        "ffmpeg": get_ffmpeg_status,
    }
    fn = mapping.get(name.lower())
    if not fn:
        return None
    return await fn()


def status_to_dict(info: EngineStatusInfo) -> dict[str, Any]:
    return {
        "name": info.name,
        "display_name": info.display_name,
        "description": info.description,
        "available": info.available,
        "enabled": info.enabled,
        "version": info.version,
        "endpoint": info.endpoint,
        "message": info.message,
        "supports": info.supports,
        "config": info.config,
        "active_tasks": info.active_tasks,
        "runtime": info.runtime,
        "process_control": info.process_control,
    }


async def get_system_summary() -> dict[str, Any]:
    s = load_settings()
    engines = await get_all_engine_status()
    return {
        "download_dir": resolve_download_dir(s.download.default_dir),
        "max_concurrent": s.download.max_concurrent,
        "server_url": f"http://{s.server.host}:{s.server.port}",
        "engines_total": len(engines),
        "engines_available": sum(1 for e in engines if e.available),
        "engines": [status_to_dict(e) for e in engines],
    }
