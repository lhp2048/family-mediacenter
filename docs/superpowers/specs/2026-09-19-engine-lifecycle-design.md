# Engine lifecycle (yt-dlp / ffmpeg / aria2)

Date: 2026-09-19  
Product: family-mediacenter  
Status: approved design (pending implementation plan)

## Goal

On the **下载组件** page, operators can manage a subset of engines without leaving the UI:

- **yt-dlp** / **ffmpeg**: install, check for updates, update, refresh status
- **aria2**: start / stop / restart the **local** `aria2c` RPC process only

Alist stays status + settings only (out of scope).

## Non-goals (this phase)

- Alist install / update / restart
- Docker / docker-compose aria2 management
- Restarting the Media Center service itself (`service.sh restart`)
- User-supplied shell commands or arbitrary package args
- Auto-convert / download-pipeline hooks

## Capability matrix

| Engine | install | check_update | update | start | stop | restart |
|--------|---------|--------------|--------|-------|------|---------|
| ytdlp | yes (venv pip) | yes (local vs PyPI) | yes (pip -U) | — | — | refresh status only |
| ffmpeg | yes (brew/scoop if present; else return copyable commands) | yes (outdated via brew/scoop) | yes (brew/scoop upgrade) | — | — | refresh status only |
| aria2 | no | optional local `-v` only | no | yes | yes | yes (local process) |
| alist | no | no | no | no | no | no |

Unsupported action for an engine → HTTP 400 with clear message.

## Architecture

```
components UI ──POST /api/v1/engines/{name}/actions──► engine_lifecycle service
                      │                                    │
                      │                                    ├─ fixed command templates
                      │                                    └─ in-memory Job (pending|running|completed|failed)
                      └─GET /api/v1/engines/actions/{job_id} (poll)
```

New module: `app/services/engine_lifecycle.py` (pattern aligned with `ffmpeg_convert` jobs).

Wire from existing engines API surface (same router / API Key as other write endpoints).

### API

```
POST /api/v1/engines/{name}/actions
Authorization: X-API-Key (when configured)

Body: { "action": "install" | "check_update" | "update" | "restart" | "start" | "stop" }

Response: {
  "id": "<job_id>",
  "engine": "ytdlp",
  "action": "update",
  "status": "pending",
  "message": "...",
  "detail": "",
  "local_version": "",
  "remote_version": "",
  "ok": false
}

GET /api/v1/engines/actions/{job_id}
→ same job payload; poll until completed|failed
```

`name`: `ytdlp` | `ffmpeg` | `aria2` (alist rejected for all lifecycle actions).

**Concurrency**: if the same `(engine, action)` is already `pending|running`, return the existing job instead of starting a second one.

### Command policy (security)

- Only fixed argv templates; never interpolate free-form user strings into a shell.
- yt-dlp uses project `.venv` Python: `python -m pip install -U yt-dlp` (create/use existing venv as install scripts do).
- ffmpeg: detect `brew` or `scoop`; run `brew install|upgrade ffmpeg` / `scoop install|update ffmpeg`. If neither exists, fail with platform install help text (same content spirit as settings install help).
- Paths for binaries continue to resolve via existing `resolve_ytdlp_executable` / `resolve_ffmpeg_executable` / PATH `aria2c`.
- Working directory: project root where relevant; env via existing `subprocess_env()`.

## Engine-specific behavior

### yt-dlp

- **install**: pip install into project `.venv`; on success optionally ensure `engines.ytdlp_path` remains usable (default name `yt-dlp` already prefers `.venv/bin`).
- **check_update**: compare installed version (`yt-dlp --version`) to latest on PyPI (JSON API or `pip index versions`); message indicates up-to-date vs newer available.
- **update**: `pip install -U yt-dlp`.
- **restart**: re-run status probe only (CLI tool has no daemon); UI label **刷新**.

### ffmpeg

- **install / update**: brew or scoop as above; Windows without scoop → failed + help; Linux without brew → failed + apt/static-build help text (no auto apt in this phase unless clearly safe—default: return commands only on Linux).
- **check_update**: brew/scoop outdated; if unmanaged binary (manual download), report local version only and say automatic update unavailable.
- **restart**: refresh status; UI label **刷新**.

### aria2 (local process only)

- Binary: `aria2c` on PATH (or common Homebrew locations).
- **start**: if RPC already reachable (existing status check), no-op success. Else spawn background:
  - `aria2c --enable-rpc --rpc-listen-all=false --rpc-listen-port=<port from engines.aria2.rpc_url>`
  - if `engines.aria2.secret` set: `--rpc-secret=<secret>`
- **stop**: terminate only processes that look like **this** RPC instance (command line contains enable-rpc and matching listen port). Never kill unrelated aria2.
- **restart**: stop then start.
- No Docker detection or compose restart.

## UI

File: `app/web/templates/partials/components_status.html` (+ small JS in `components.html`).

Per card:

- ytdlp / ffmpeg: 安装 · 检查更新 · 更新 · 刷新
- aria2: 启动 · 停止 · 重启
- alist: unchanged (检测连接 · 去配置)
- Shared: 检测连接 remains for all

While a job runs for that engine: disable that engine’s lifecycle buttons; show short status text from job `message`. On terminal state: refresh components partial / health.

## Error handling

- Missing tool / package manager / network → `failed` with human message + copyable fallback commands.
- Permission errors → same.
- Job stderr truncated to last ~12 lines in `detail`.
- API Key behavior matches other protected routes.

## Testing & docs

- `scripts/test_engine_lifecycle.py`: unit-ish smoke; skip cases when tools missing; assert action whitelist and job polling shape.
- Update `skills/family-mediacenter/references/api.md` (+ brief SKILL note).

## Acceptance checklist

1. Components page shows correct buttons per engine.
2. With project venv, yt-dlp install/update can make `/health` engines.ytdlp true.
3. With local `aria2c`, restart restores aria2 available in health when RPC port matches config.
4. Unsupported actions (e.g. alist install, aria2 install) return 400.
5. Smoke script exits 0 (skips allowed).
6. API docs document the new endpoints.

## Open implementation notes

- Linux ffmpeg auto-install deferred: return commands only unless brew exists.
- PyPI check may need short timeout; failure → soft message “无法检查远程版本”.
- Windows process stop for aria2: use best-effort (taskkill / WMI filter); document limitation if cmdline matching is weaker than Unix.
