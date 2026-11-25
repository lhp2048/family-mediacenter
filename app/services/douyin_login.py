"""Douyin QR login via the official page in local Chrome, saved for yt-dlp."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import signal
import socket
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
import websockets

from app.config import DATA_DIR, PROJECT_ROOT

DOUYIN_COOKIES_REL = "data/douyin_cookies.txt"
DOUYIN_META_REL = "data/douyin_login.json"
LOGIN_PAGE = "https://www.douyin.com/login_page?service=https%3A%2F%2Fwww.douyin.com"
SESSION_TTL_SEC = 180
QR_WAIT_SEC = 20

DOUYIN_COOKIE_NAMES = (
    "sessionid",
    "sessionid_ss",
    "sid_tt",
    "uid_tt",
    "uid_tt_ss",
    "sid_guard",
    "ttwid",
    "odin_tt",
    "passport_csrf_token",
    "passport_csrf_token_default",
    "msToken",
    "s_v_web_id",
    "sid_ucp_v1",
    "ssid_ucp_v1",
)

_STATE_MESSAGE = {
    "waiting": "请使用抖音 App 扫描二维码",
    "scanned": "扫码成功，请在手机上确认登录",
    "expired": "二维码已过期，请重新获取",
    "success": "登录成功，Cookie 已保存",
    "error": "抖音登录失败",
}


_DEVTOOLS_PORT = re.compile(r"ws://(?:127\.0\.0\.1|\[::1\]):(\d+)/")
_PROFILE_DIR = DATA_DIR / "douyin_chrome_profile"


def devtools_port(text: str) -> int | None:
    match = _DEVTOOLS_PORT.search(text or "")
    return int(match.group(1)) if match else None


def find_chrome() -> str | None:
    candidates: list[str] = []
    if sys.platform == "darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            str(Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        ]
    elif sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        program = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        program_x86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
        candidates = [
            str(Path(program) / "Google/Chrome/Application/chrome.exe"),
            str(Path(program_x86) / "Google/Chrome/Application/chrome.exe"),
            str(Path(local) / "Google/Chrome/Application/chrome.exe") if local else "",
        ]
    else:
        for name in ("google-chrome", "google-chrome-stable", "chromium-browser", "chromium"):
            found = shutil.which(name)
            if found:
                return found
    for path in candidates:
        if path and Path(path).is_file():
            return path
    return None


def _chrome_start_error(detail: str) -> str:
    line = ""
    for item in reversed((detail or "").splitlines()):
        item = item.strip()
        if item and "DevTools listening" not in item:
            line = item
            break
    if not line:
        return "Google Chrome 已安装，但后台服务没有把它启动起来"
    return f"无法启动本机 Google Chrome：{line[:180]}"


_CHROME_ARGS = (
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-extensions",
    "--use-mock-keychain",
    "--password-store=basic",
)


@dataclass
class ChromePipe:
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    pending: dict[int, asyncio.Future] = field(default_factory=dict)
    msg_id: int = 0
    task: asyncio.Task | None = None

    def start(self) -> None:
        self.task = asyncio.create_task(self._read())

    async def _read(self) -> None:
        buf = b""
        try:
            while True:
                chunk = await self.reader.read(65536)
                if not chunk:
                    raise RuntimeError("Chrome 调试连接已断开")
                buf += chunk
                while b"\0" in buf:
                    raw, buf = buf.split(b"\0", 1)
                    if not raw.strip():
                        continue
                    data = json.loads(raw)
                    mid = data.get("id")
                    fut = self.pending.get(mid) if isinstance(mid, int) else None
                    if fut is not None and not fut.done():
                        fut.set_result(data)
        except Exception as exc:
            for fut in self.pending.values():
                if not fut.done():
                    fut.set_exception(exc)

    async def call(
        self,
        method: str,
        params: dict | None = None,
        session_id: str = "",
        timeout: float = 20,
    ) -> dict:
        self.msg_id += 1
        message_id = self.msg_id
        payload: dict[str, Any] = {"id": message_id, "method": method}
        if params is not None:
            payload["params"] = params
        if session_id:
            payload["sessionId"] = session_id
        raw = json.dumps(payload).encode("utf-8")
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self.pending[message_id] = fut
        self.writer.write(raw + b"\0")
        await self.writer.drain()
        try:
            data = await asyncio.wait_for(fut, timeout)
        finally:
            self.pending.pop(message_id, None)
        if isinstance(data, dict) and data.get("error"):
            message = data["error"].get("message") or method
            raise RuntimeError(str(message))
        result = data.get("result") if isinstance(data, dict) else None
        return result if isinstance(result, dict) else {}


class _ChromeProcess:
    def __init__(self, pid: int) -> None:
        self.pid = pid
        self._returncode: int | None = None

    @property
    def returncode(self) -> int | None:
        if self._returncode is not None:
            return self._returncode
        try:
            waited, status = os.waitpid(self.pid, os.WNOHANG)
        except ChildProcessError:
            self._returncode = 0
            return self._returncode
        if waited == 0:
            return None
        self._returncode = os.waitstatus_to_exitcode(status)
        return self._returncode

    def terminate(self) -> None:
        if self.returncode is None:
            try:
                os.kill(self.pid, signal.SIGTERM)
            except ProcessLookupError:
                self._returncode = 0

    def kill(self) -> None:
        try:
            os.kill(self.pid, signal.SIGKILL)
        except ProcessLookupError:
            self._returncode = 0

    async def wait(self) -> int:
        while self.returncode is None:
            await asyncio.sleep(0.05)
        return self.returncode or 0


@dataclass
class BrowserSession:
    proc: Any
    ws: Any
    port: int
    created_at: float
    owns_process: bool = False
    msg_id: int = 0
    stderr: str = ""
    stderr_task: asyncio.Task | None = field(default=None)
    pipe: ChromePipe | None = None
    cdp_session: str = ""


_sessions: dict[str, BrowserSession] = {}


def netscape_has_cookie(text: str, name: str) -> bool:
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7 and parts[5] == name and parts[6]:
            return True
    return False


def cookies_to_netscape(cookies: dict[str, str]) -> str:
    lines = [
        "# Netscape HTTP Cookie File",
        "# Generated by Family Media Center",
        "",
    ]
    written: set[str] = set()
    for name in DOUYIN_COOKIE_NAMES:
        value = cookies.get(name)
        if value:
            lines.append(f".douyin.com\tTRUE\t/\tFALSE\t0\t{name}\t{value}")
            written.add(name)
    for name, value in cookies.items():
        if name in written or not value:
            continue
        lines.append(f".douyin.com\tTRUE\t/\tFALSE\t0\t{name}\t{value}")
    if not netscape_has_login("\n".join(lines)):
        raise ValueError("登录成功但未获取到抖音 Cookie")
    return "\n".join(lines) + "\n"


def cookies_from_browser_list(cookies: list[dict[str, Any]]) -> dict[str, str]:
    found: dict[str, str] = {}
    for item in cookies:
        domain = str(item.get("domain") or "")
        name = str(item.get("name") or "")
        value = str(item.get("value") or "")
        if "douyin.com" not in domain or not name or not value:
            continue
        found[name] = value
    return found


LOGIN_COOKIE_NAMES = ("sessionid", "sessionid_ss", "sid_tt")


def has_login_cookie(names: set[str]) -> bool:
    return any(name in names for name in LOGIN_COOKIE_NAMES)


def netscape_has_login(text: str) -> bool:
    return any(netscape_has_cookie(text, name) for name in LOGIN_COOKIE_NAMES)


def login_page_state(text: str, cookie_names: set[str], has_qr: bool = False) -> str:
    """waiting | scanned | success | expired."""
    if has_login_cookie(cookie_names):
        return "success"
    body = text or ""
    if any(phrase in body for phrase in ("扫码成功", "确认登录", "请在手机上确认", "已扫描")):
        return "scanned"
    if has_qr:
        return "waiting"
    if any(phrase in body for phrase in ("二维码已过期", "二维码失效", "已失效", "请刷新二维码")):
        return "expired"
    return "waiting"


def save_douyin_cookies(cookies: dict[str, str]) -> Path:
    if not has_login_cookie(set(cookies)):
        raise ValueError("登录成功但未获取到抖音登录 Cookie")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = PROJECT_ROOT / DOUYIN_COOKIES_REL
    path.write_text(cookies_to_netscape(cookies), encoding="utf-8")
    meta = {
        "logged_in_at": datetime.now(timezone.utc).isoformat(),
        "uid": cookies.get("uid_tt", ""),
        "cookies_file": DOUYIN_COOKIES_REL,
    }
    (PROJECT_ROOT / DOUYIN_META_REL).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def get_douyin_login_status() -> dict[str, Any]:
    path = PROJECT_ROOT / DOUYIN_COOKIES_REL
    meta_path = PROJECT_ROOT / DOUYIN_META_REL
    meta: dict[str, Any] = {}
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            meta = {}
    logged_in = False
    updated = meta.get("logged_in_at")
    if path.is_file():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        logged_in = netscape_has_login(text)
        if logged_in:
            updated = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
    return {
        "logged_in": logged_in,
        "cookies_file": DOUYIN_COOKIES_REL,
        "updated_at": updated,
        "uid": meta.get("uid", "") if logged_in else "",
    }


_op_lock = asyncio.Lock()


def _browser_connected(session: BrowserSession) -> bool:
    if session.proc is not None and session.proc.returncode is not None:
        return False
    if session.pipe is not None:
        return True
    if session.ws is None:
        return False
    try:
        return session.ws.close_code is None
    except Exception:
        return False


def _only_session() -> tuple[str, BrowserSession | None]:
    if not _sessions:
        return "", None
    session_id, session = next(iter(_sessions.items()))
    return session_id, session


async def _stop_process(proc: Any) -> None:
    if proc.returncode is not None:
        return
    proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=3)
    except (asyncio.TimeoutError, ProcessLookupError):
        try:
            proc.kill()
        except (ProcessLookupError, OSError):
            pass


async def _close_session(session_id: str) -> None:
    session = _sessions.pop(session_id, None)
    if not session:
        return
    if session.stderr_task:
        session.stderr_task.cancel()
    if session.pipe is not None and session.pipe.task is not None:
        session.pipe.task.cancel()
        session.pipe.writer.close()
    if session.ws is not None:
        try:
            await session.ws.close()
        except Exception:
            pass
    if session.proc is not None:
        await _stop_process(session.proc)
    await _kill_chrome_profile(_PROFILE_DIR)
    shutil.rmtree(_PROFILE_DIR, ignore_errors=True)


async def _cleanup_sessions() -> None:
    now = time.time()
    expired = [
        key for key, session in _sessions.items() if now - session.created_at > SESSION_TTL_SEC
    ]
    for key in expired:
        await _close_session(key)


async def _kill_chrome_profile(profile: Path) -> None:
    if sys.platform == "win32":
        return
    proc = await asyncio.create_subprocess_exec(
        "pkill",
        "-f",
        f"user-data-dir={profile}",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        await asyncio.wait_for(proc.wait(), timeout=3)
    except asyncio.TimeoutError:
        pass


def _free_port() -> int:
    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def _chrome_app_bundle(chrome: str) -> Path | None:
    for parent in Path(chrome).parents:
        if parent.suffix == ".app":
            return parent
    return None


def _chrome_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("HOME", str(Path.home()))
    env.setdefault("TMPDIR", "/tmp")
    env.setdefault("LANG", "en_US.UTF-8")
    return env


def _active_port() -> int | None:
    path = _PROFILE_DIR / "DevToolsActivePort"
    try:
        line = path.read_text(encoding="utf-8").splitlines()[0].strip()
    except (OSError, IndexError):
        return None
    try:
        return int(line)
    except ValueError:
        return None


async def _devtools_ready(port: int) -> bool:
    async with httpx.AsyncClient(timeout=0.5) as client:
        for host in (f"127.0.0.1:{port}", f"[::1]:{port}"):
            try:
                response = await client.get(f"http://{host}/json/version")
                if response.status_code == 200:
                    return True
            except httpx.HTTPError:
                continue
    return False


def _chrome_exit_error(code: int | None, detail: str) -> str:
    text = _chrome_start_error(detail)
    if code is None:
        return text
    if text == "Google Chrome 已安装，但后台服务没有把它启动起来":
        return f"Google Chrome 已安装，但进程退出了（代码 {code}）"
    return f"{text}（代码 {code}）"


async def _launch_direct(chrome: str) -> tuple[asyncio.subprocess.Process, int, str]:
    proc = await asyncio.create_subprocess_exec(
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--remote-debugging-address=127.0.0.1",
        *_CHROME_ARGS,
        "--remote-debugging-port=0",
        f"--user-data-dir={_PROFILE_DIR}",
        "about:blank",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=_chrome_env(),
    )
    assert proc.stdout is not None
    buffered = ""
    deadline = time.time() + 15
    try:
        while time.time() < deadline:
            port = _active_port() or devtools_port(buffered)
            if port and await _devtools_ready(port):
                return proc, port, buffered
            if proc.returncode is not None:
                rest = await proc.stdout.read()
                buffered += rest.decode(errors="replace")
                raise RuntimeError(_chrome_exit_error(proc.returncode, buffered))
            try:
                chunk = await asyncio.wait_for(proc.stdout.read(512), timeout=0.3)
            except asyncio.TimeoutError:
                chunk = b""
            if chunk:
                buffered += chunk.decode(errors="replace")
        raise RuntimeError(_chrome_exit_error(proc.returncode, buffered))
    except Exception:
        await _stop_process(proc)
        raise


async def _launch_via_open(chrome: str, port: int) -> int:
    app = _chrome_app_bundle(chrome)
    if app is None or not Path("/usr/bin/open").is_file():
        raise RuntimeError("无法通过启动服务打开 Google Chrome")
    proc = await asyncio.create_subprocess_exec(
        "/usr/bin/open",
        "-g",
        "-na",
        str(app),
        "--args",
        *_CHROME_ARGS,
        "--new-window",
        "--window-position=-2400,-2400",
        "--window-size=900,700",
        f"--remote-debugging-port={port}",
        f"--user-data-dir={_PROFILE_DIR}",
        LOGIN_PAGE,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
        env=_chrome_env(),
    )
    _, err = await proc.communicate()
    if proc.returncode != 0:
        detail = err.decode(errors="replace").strip()
        raise RuntimeError(detail or "无法通过启动服务打开 Google Chrome")
    deadline = time.time() + 20
    while time.time() < deadline:
        active = _active_port() or port
        if await _devtools_ready(active):
            return active
        await asyncio.sleep(0.2)
    raise RuntimeError("Google Chrome 已安装，但后台服务没有把它启动起来")


async def _drain_stderr(session: BrowserSession) -> None:
    if session.proc is None:
        return
    stream = session.proc.stderr or session.proc.stdout
    if stream is None:
        return
    while True:
        chunk = await stream.read(1024)
        if not chunk:
            return
        session.stderr = (session.stderr + chunk.decode(errors="replace"))[-2000:]


async def _cdp(session: BrowserSession, method: str, params: dict | None = None, timeout: float = 20) -> dict:
    if session.pipe is not None:
        return await session.pipe.call(method, params, session.cdp_session, timeout)
    session.msg_id += 1
    message_id = session.msg_id
    payload: dict[str, Any] = {"id": message_id, "method": method}
    if params is not None:
        payload["params"] = params
    await session.ws.send(json.dumps(payload))
    deadline = time.time() + timeout
    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            raise TimeoutError(method)
        raw = await asyncio.wait_for(session.ws.recv(), timeout=remaining)
        data = json.loads(raw)
        if data.get("id") != message_id:
            continue
        if data.get("error"):
            message = data["error"].get("message") or method
            raise RuntimeError(str(message))
        result = data.get("result")
        return result if isinstance(result, dict) else {}


_QR_EXPR = """(() => {
  const img = [...document.images].find((el) => {
    const src = el.src || '';
    return src.startsWith('data:image') && src.length > 500;
  });
  return img ? img.src : '';
})()"""


async def _evaluate(session: BrowserSession, expression: str) -> Any:
    result = await _cdp(
        session,
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True},
    )
    remote = result.get("result") if isinstance(result.get("result"), dict) else {}
    return remote.get("value")


async def _read_qr_image(session: BrowserSession) -> str:
    value = await _evaluate(session, _QR_EXPR)
    return value if isinstance(value, str) else ""


def _log_tail(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-1500:]
    except OSError:
        return ""


async def _chrome_stdio(read_fd: int, write_fd: int) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader(limit=16_000_000)
    await loop.connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(reader),
        os.fdopen(read_fd, "rb", buffering=0),
    )
    write_protocol = asyncio.streams.FlowControlMixin(loop)
    write_transport, _ = await loop.connect_write_pipe(lambda: write_protocol, os.fdopen(write_fd, "wb", buffering=0))
    return reader, asyncio.StreamWriter(write_transport, write_protocol, None, loop)


def _spawn_chrome(chrome: str, log_fd: int, cmd_read: int, cmd_write: int, rsp_read: int, rsp_write: int) -> _ChromeProcess:
    """Put the debug pipe on fds 3 and 4 inside Chrome. preexec_fn does not survive Python 3.13."""
    null_fd = os.open(os.devnull, os.O_RDWR)
    actions: list[tuple] = [
        (os.POSIX_SPAWN_DUP2, cmd_read, 3),
        (os.POSIX_SPAWN_DUP2, rsp_write, 4),
        (os.POSIX_SPAWN_DUP2, null_fd, 0),
        (os.POSIX_SPAWN_DUP2, null_fd, 1),
        (os.POSIX_SPAWN_DUP2, log_fd, 2),
    ]
    closed: set[int] = set()
    for fd in (cmd_read, cmd_write, rsp_read, rsp_write, null_fd, log_fd):
        if fd > 4 and fd not in closed:
            actions.append((os.POSIX_SPAWN_CLOSE, fd))
            closed.add(fd)
    argv = [
        chrome,
        "--remote-debugging-pipe",
        *_CHROME_ARGS,
        "--new-window",
        "--window-size=1000,800",
        f"--user-data-dir={_PROFILE_DIR}",
        LOGIN_PAGE,
    ]
    try:
        pid = os.posix_spawn(chrome, argv, _chrome_env(), file_actions=actions)
    finally:
        os.close(null_fd)
    return _ChromeProcess(pid)


async def _launch_visible(chrome: str) -> tuple[_ChromeProcess, ChromePipe, str]:
    """Talk to Chrome on fds 3 and 4. launchd never exposes the TCP debug port."""
    log_path = _PROFILE_DIR / "chrome.log"
    log_fd = os.open(str(log_path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    cmd_read, cmd_write = os.pipe()
    rsp_read, rsp_write = os.pipe()
    try:
        proc = _spawn_chrome(chrome, log_fd, cmd_read, cmd_write, rsp_read, rsp_write)
    except Exception:
        os.close(rsp_read)
        os.close(cmd_write)
        raise
    finally:
        os.close(log_fd)
        os.close(cmd_read)
        os.close(rsp_write)
    reader, writer = await _chrome_stdio(rsp_read, cmd_write)
    pipe = ChromePipe(reader=reader, writer=writer)
    pipe.start()
    deadline = time.time() + 20
    target_id = ""
    try:
        while time.time() < deadline and not target_id:
            if proc.returncode is not None:
                raise RuntimeError(_chrome_exit_error(proc.returncode, _log_tail(log_path)))
            try:
                result = await pipe.call("Target.getTargets", timeout=3)
            except Exception:
                await asyncio.sleep(0.3)
                continue
            infos = result.get("targetInfos") if isinstance(result.get("targetInfos"), list) else []
            page = next(
                (
                    item
                    for item in infos
                    if isinstance(item, dict)
                    and item.get("type") == "page"
                    and "douyin.com" in str(item.get("url") or "")
                ),
                None,
            )
            if page is None:
                page = next(
                    (
                        item
                        for item in infos
                        if isinstance(item, dict) and item.get("type") == "page"
                    ),
                    None,
                )
            if isinstance(page, dict) and page.get("targetId"):
                target_id = str(page["targetId"])
                break
            await asyncio.sleep(0.3)
        if not target_id:
            created = await pipe.call("Target.createTarget", {"url": LOGIN_PAGE})
            target_id = str(created.get("targetId") or "")
        if not target_id:
            raise RuntimeError("Chrome 已打开，但没有拿到登录页")
        attached = await pipe.call(
            "Target.attachToTarget",
            {"targetId": target_id, "flatten": True},
        )
        cdp_session = str(attached.get("sessionId") or "")
        if not cdp_session:
            raise RuntimeError("Chrome 已打开，但没有连上登录页")
        await pipe.call("Network.enable", session_id=cdp_session)
        await pipe.call("Page.enable", session_id=cdp_session)
        return proc, pipe, cdp_session
    except Exception:
        if pipe.task is not None:
            pipe.task.cancel()
        pipe.writer.close()
        await _stop_process(proc)
        await _kill_chrome_profile(_PROFILE_DIR)
        raise


async def _wait_for_qr(session: BrowserSession) -> str:
    deadline = time.time() + QR_WAIT_SEC
    while time.time() < deadline:
        src = await _read_qr_image(session)
        if src:
            if src.startswith("data:image") and "," in src:
                return src.split(",", 1)[1]
            return src
        await asyncio.sleep(0.5)
    try:
        shot = await _cdp(session, "Page.captureScreenshot", {"format": "png"})
    except Exception:
        shot = {}
    data = shot.get("data") if isinstance(shot, dict) else ""
    if isinstance(data, str) and len(data) > 500:
        return data
    raise RuntimeError("未能从抖音登录页获取二维码")


async def _launch_session() -> tuple[str, BrowserSession]:
    chrome = find_chrome()
    if not chrome:
        raise RuntimeError("未找到本机 Google Chrome，无法发起抖音扫码登录")
    await _prepare_profile()
    if sys.platform == "darwin":
        proc, pipe, cdp_session = await _launch_visible(chrome)
        session = BrowserSession(
            proc=proc,
            ws=None,
            port=0,
            created_at=time.time(),
            owns_process=True,
            pipe=pipe,
            cdp_session=cdp_session,
        )
        return await _attach_page(session)
    proc, port, buffered = await _launch_direct(chrome)
    session = BrowserSession(
        proc=proc,
        ws=None,
        port=port,
        created_at=time.time(),
        owns_process=True,
        stderr=buffered[-2000:],
    )
    session.stderr_task = asyncio.create_task(_drain_stderr(session))
    return await _attach_page(session)


async def _prepare_profile() -> None:
    await _kill_chrome_profile(_PROFILE_DIR)
    shutil.rmtree(_PROFILE_DIR, ignore_errors=True)
    _PROFILE_DIR.mkdir(parents=True, exist_ok=True)


async def _page_targets(port: int) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=3) as client:
        try:
            response = await client.get(f"http://127.0.0.1:{port}/json/list")
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError:
            return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict) and item.get("type") == "page"]


async def _connect_page(session: BrowserSession) -> bool:
    if session.pipe is not None:
        return bool(session.cdp_session) and _browser_connected(session)
    if session.ws is not None:
        try:
            if session.ws.close_code is None:
                return True
        except Exception:
            pass
        try:
            await session.ws.close()
        except Exception:
            pass
        session.ws = None
    pages = await _page_targets(session.port)
    if not pages:
        if not await _devtools_ready(session.port):
            return False
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.put(
                f"http://127.0.0.1:{session.port}/json/new?{quote(LOGIN_PAGE, safe='')}"
            )
            response.raise_for_status()
            created = response.json()
        pages = [created] if isinstance(created, dict) else []
    chosen = next((page for page in pages if "douyin.com" in str(page.get("url") or "")), None)
    if chosen is None and pages:
        chosen = pages[0]
    ws_url = str((chosen or {}).get("webSocketDebuggerUrl") or "")
    if not ws_url:
        return False
    session.ws = await websockets.connect(ws_url, max_size=8_000_000)
    await _cdp(session, "Network.enable")
    await _cdp(session, "Page.enable")
    return True


async def _attach_page(session: BrowserSession) -> tuple[str, BrowserSession]:
    try:
        if not await _connect_page(session):
            raise RuntimeError("无法连接本机 Google Chrome 调试端口")
    except Exception as exc:
        session_id = uuid.uuid4().hex
        _sessions[session_id] = session
        await _close_session(session_id)
        if isinstance(exc, RuntimeError):
            raise
        raise RuntimeError(_chrome_start_error(session.stderr or str(exc))) from exc
    session_id = uuid.uuid4().hex
    _sessions[session_id] = session
    return session_id, session


async def _open_qr(session: BrowserSession) -> str:
    await _cdp(session, "Page.navigate", {"url": LOGIN_PAGE}, timeout=30)
    return await _wait_for_qr(session)


async def _start_qr_locked() -> dict[str, str]:
    await _cleanup_sessions()
    session_id, session = _only_session()
    if session is not None and not _browser_connected(session):
        await _close_session(session_id)
        session = None
    last_error: Exception | None = None
    for attempt in range(2):
        if session is None or attempt:
            if session_id:
                await _close_session(session_id)
            session_id, session = await _launch_session()
        try:
            image = await _open_qr(session)
        except Exception as exc:
            last_error = exc
            session = None
            continue
        session.created_at = time.time()
        return {"session_id": session_id, "url": "", "qrcode_base64": image}
    if session_id:
        await _close_session(session_id)
    if last_error:
        raise last_error
    raise RuntimeError("未能从抖音登录页获取二维码")


async def start_qr_login() -> dict[str, str]:
    async with _op_lock:
        return await _start_qr_locked()


async def _page_snapshot(session: BrowserSession) -> tuple[str, dict[str, str]]:
    try:
        text = await _evaluate(session, "document.body ? document.body.innerText : ''")
    except Exception:
        text = ""
    if not isinstance(text, str):
        text = ""
    raw: list[Any] = []
    for method, params in (
        ("Network.getAllCookies", None),
        (
            "Network.getCookies",
            {"urls": ["https://www.douyin.com/", "https://www.iesdouyin.com/", "https://login.douyin.com/"]},
        ),
    ):
        try:
            result = await _cdp(session, method, params)
        except Exception:
            continue
        found = result.get("cookies") if isinstance(result.get("cookies"), list) else []
        if found:
            raw = found
            break
    return text, cookies_from_browser_list(raw)


async def poll_qr_login(session_id: str) -> dict[str, Any]:
    async with _op_lock:
        await _cleanup_sessions()
        session = _sessions.get(session_id)
        if not session or not _browser_connected(session):
            await _close_session(session_id)
            return {"status": "expired", "message": "会话已过期，请重新扫码"}
        try:
            connected = await _connect_page(session)
        except Exception:
            connected = False
        if not connected:
            await _close_session(session_id)
            return {"status": "expired", "message": "会话已过期，请重新扫码"}

        text, cookies = await _page_snapshot(session)
        try:
            has_qr = bool(await _read_qr_image(session))
        except Exception:
            has_qr = False
        state = login_page_state(text, set(cookies), has_qr=has_qr)
        if state == "success":
            try:
                path = save_douyin_cookies(cookies)
            except ValueError as exc:
                await _close_session(session_id)
                return {"status": "error", "message": str(exc)}
            await _close_session(session_id)
            return {
                "status": "success",
                "message": _STATE_MESSAGE["success"],
                "cookies_file": DOUYIN_COOKIES_REL,
                "path": str(path),
            }
        if state == "expired":
            await _close_session(session_id)
            return {"status": "expired", "message": _STATE_MESSAGE["expired"]}
        return {"status": state, "message": _STATE_MESSAGE[state]}


async def cancel_qr_login(session_id: str) -> dict[str, str]:
    async with _op_lock:
        await _close_session(session_id)
        return {"status": "cancelled"}
