# Engine Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add install / check_update / update / refresh for yt-dlp & ffmpeg, and start / stop / restart for local aria2c, from the components page.

**Architecture:** In-memory async jobs in `engine_lifecycle.py`; REST under `/api/v1/engines/.../actions`; components UI polls jobs. Fixed argv only.

**Tech Stack:** FastAPI, asyncio subprocess, httpx (PyPI), existing engine_status helpers.

## Global Constraints

- Scope: ytdlp, ffmpeg, aria2 only; alist lifecycle rejected with 400
- No Docker aria2; no Media Center service restart
- Never interpolate user shell; API Key same as other write routes
- Spec: `docs/superpowers/specs/2026-09-19-engine-lifecycle-design.md`

---

### Task 1: Lifecycle service + API

**Files:**
- Create: `app/services/engine_lifecycle.py`
- Modify: `app/api/routes.py` (add action endpoints after engine test)

**Produces:** `lifecycle_service.start_action(engine, action) -> LifecycleJob`, `get_job(id)`

- [ ] Implement service with whitelist, jobs, ytdlp/ffmpeg/aria2 handlers
- [ ] Wire POST `/engines/{name}/actions` and GET `/engines/actions/{job_id}`
- [ ] Smoke: unsupported action → 400; restart ytdlp → completed refresh

### Task 2: Components UI

**Files:**
- Modify: `app/web/templates/partials/components_status.html`
- Modify: `app/web/templates/components.html`

- [ ] Buttons per engine + JS poll `engineAction(name, action)`

### Task 3: Docs + smoke script

**Files:**
- Create: `scripts/test_engine_lifecycle.py`
- Modify: `skills/family-mediacenter/references/api.md`
- Modify: `skills/family-mediacenter/SKILL.md` (brief)

- [ ] Document endpoints; smoke exits 0

---

Plan saved; executing inline (user requested 开始).
