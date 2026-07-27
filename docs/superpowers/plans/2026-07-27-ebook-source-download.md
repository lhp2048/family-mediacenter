# E-Book Source File Download Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users force-download e-book source files from the materials Web UI via `GET /files/{path}?download=1`.

**Architecture:** Extend `serve_public_file` to switch `Content-Disposition` between `inline` and `attachment` based on a `download` query flag. Add a 「下载」 button on the materials preview toolbar that hits `public_url?download=1`. Document the flag in the skill API reference.

**Tech Stack:** FastAPI `FileResponse`, Alpine.js materials page (`materials.html`), existing `/files/` serving + `files.public_access` auth.

## Global Constraints

- Chinese UI copy for the button: `下载`
- Only Web materials page (not embed reader, not new materials API)
- Default `/files/` behavior must remain `inline`
- `download` truthy values: `1`, `true` (case-insensitive); everything else → inline
- Filename for attachment = `Path(target).name` (basename only)
- Do not commit secrets or change git config

## File Map

| File | Role |
|------|------|
| `app/api/files.py` | Parse `download` query; set disposition + filename |
| `app/web/templates/materials.html` | Preview toolbar download button + JS helper |
| `skills/family-mediacenter/references/api.md` | Document `?download=1` |
| `scripts/test_file_download_disposition.py` | Smoke test for disposition headers |

---

### Task 1: Backend `?download=1` on `/files/...`

**Files:**
- Modify: `app/api/files.py`
- Create: `scripts/test_file_download_disposition.py`
- Spec: `docs/superpowers/specs/2026-07-27-ebook-source-download-design.md`

**Interfaces:**
- Consumes: existing `get_file_for_serve(file_path)`, `media_type_for_path(target)`, `load_settings().files.public_access`
- Produces: `serve_public_file(..., download: Optional[str] = Query(None))` → `FileResponse` with `content_disposition_type` `"attachment"` when download is truthy, else `"inline"`; when attachment, pass `filename=target.name`

- [ ] **Step 1: Write the failing smoke test**

Create `scripts/test_file_download_disposition.py`:

```python
#!/usr/bin/env python3
"""Smoke-test Content-Disposition for GET /files/...?download=1."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from fastapi.testclient import TestClient

    from app.config import PROJECT_ROOT
    from app.main import app

    ebooks = PROJECT_ROOT / "downloads" / "ebooks"
    ebooks.mkdir(parents=True, exist_ok=True)
    probe = ebooks / "_download_probe.txt"
    probe.write_text("download-probe\n", encoding="utf-8")
    rel = "ebooks/_download_probe.txt"

    try:
        client = TestClient(app)

        inline = client.get(f"/files/{rel}")
        assert inline.status_code == 200, inline.status_code
        cd_inline = inline.headers.get("content-disposition", "")
        assert "attachment" not in cd_inline.lower(), cd_inline
        # Starlette may omit disposition for inline, or include inline=
        assert "attachment" not in cd_inline.lower()

        forced = client.get(f"/files/{rel}", params={"download": "1"})
        assert forced.status_code == 200, forced.status_code
        cd = forced.headers.get("content-disposition", "")
        assert "attachment" in cd.lower(), cd
        assert "_download_probe.txt" in cd, cd
        assert forced.content == b"download-probe\n"

        for val in ("true", "TRUE"):
            r = client.get(f"/files/{rel}", params={"download": val})
            assert r.status_code == 200
            assert "attachment" in r.headers.get("content-disposition", "").lower()

        for val in ("0", "false", ""):
            r = client.get(f"/files/{rel}", params={"download": val})
            assert r.status_code == 200
            assert "attachment" not in r.headers.get("content-disposition", "").lower()

        print("OK: download disposition behavior")
        return 0
    finally:
        try:
            probe.unlink(missing_ok=True)
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/muxin/Desktop/family-smart/family-mediacenter && python scripts/test_file_download_disposition.py`

Expected: FAIL — assertion on `"attachment" in cd` (current handler always uses inline)

- [ ] **Step 3: Implement `download` query on `serve_public_file`**

Replace `serve_public_file` in `app/api/files.py` with:

```python
def _wants_download(download: Optional[str]) -> bool:
    if download is None:
        return False
    return download.strip().lower() in {"1", "true"}


@router.get("/files/{file_path:path}")
async def serve_public_file(
    request: Request,
    file_path: str,
    download: Optional[str] = Query(None),
) -> FileResponse:
    s = load_settings()
    if not s.files.public_access:
        verify_api_key(request)
    try:
        target = get_file_for_serve(file_path)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    if _wants_download(download):
        return FileResponse(
            path=target,
            media_type=media_type_for_path(target),
            filename=target.name,
            content_disposition_type="attachment",
        )
    return FileResponse(
        path=target,
        media_type=media_type_for_path(target),
        content_disposition_type="inline",
    )
```

Keep existing imports; `Optional` and `Query` are already imported.

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/test_file_download_disposition.py`

Expected: `OK: download disposition behavior` and exit code 0

- [ ] **Step 5: Commit**

```bash
git add app/api/files.py scripts/test_file_download_disposition.py
git commit -m "$(cat <<'EOF'
feat(files): support ?download=1 for attachment disposition

EOF
)"
```

---

### Task 2: Materials page 「下载」 button

**Files:**
- Modify: `app/web/templates/materials.html` (toolbar ~145–148 and JS near `openPreviewInNewTab`)

**Interfaces:**
- Consumes: `selectedEntry.public_url` / `previewUrl`, `selectedEntry.name`
- Produces: `downloadUrl()`, `downloadSelectedFile()` used by toolbar button

- [ ] **Step 1: Add toolbar button**

In the preview toolbar actions block, add the download button **before** 「新窗口」:

```html
        <div class="toolbar-actions" x-show="selectedEntry">
          <a
            class="btn small secondary"
            :href="downloadUrl()"
            :download="selectedEntry?.name || ''"
            @click="downloadSelectedFile($event)"
          >下载</a>
          <button type="button" class="btn small secondary" @click="openPreviewInNewTab()">新窗口</button>
          <button type="button" class="small secondary" @click="copyUrl(previewUrl)">复制文件链接</button>
        </div>
```

- [ ] **Step 2: Add JS helpers**

Add methods next to `openPreviewInNewTab` inside `materialsPage()`:

```javascript
    downloadUrl() {
      const base = (this.previewUrl || this.selectedEntry?.public_url || '').trim();
      if (!base) return '';
      const sep = base.includes('?') ? '&' : '?';
      return `${base}${sep}download=1`;
    },
    downloadSelectedFile(event) {
      const url = this.downloadUrl();
      if (!url) {
        if (event) event.preventDefault();
        return;
      }
      // Rely on <a download href> for same-origin; keep default navigation.
    },
```

- [ ] **Step 3: Manual verify (or skip if no server)**

If the app is running: open `/ebook` (or materials route), select a file, click 下载 — browser should save the source with the original name. Online reader iframe must keep working.

If not running: skip and note in commit body that UI is wired to Task 1 endpoint.

- [ ] **Step 4: Commit**

```bash
git add app/web/templates/materials.html
git commit -m "$(cat <<'EOF'
feat(materials): add source file download button

EOF
)"
```

---

### Task 3: API docs

**Files:**
- Modify: `skills/family-mediacenter/references/api.md` (Serve File section ~164–170)

**Interfaces:**
- Documents: `GET /files/{file_path}?download=1`

- [ ] **Step 1: Update Serve File section**

Replace the Serve File subsection with:

```markdown
### Serve File (public URL)

```
GET /files/{file_path}
GET /files/{file_path}?download=1
```

Used by playlist `public_url` and materials `public_url`. Requires API key when `files.public_access=false`.

- Default: `Content-Disposition: inline` (browser preview / streaming).
- `download=1` or `download=true`: `Content-Disposition: attachment` with the source filename (force save).
```

Also add one line under Materials browse response note (after the `public_url` example block, before Embed reader):

```markdown
To download the source file from the Web UI or clients, append `?download=1` to `public_url` (same `/files/...` endpoint).
```

- [ ] **Step 2: Commit**

```bash
git add skills/family-mediacenter/references/api.md
git commit -m "$(cat <<'EOF'
docs(api): document /files/?download=1 attachment mode

EOF
)"
```

---

## Spec Coverage Check

| Spec requirement | Task |
|------------------|------|
| `?download=1` → attachment + basename | Task 1 |
| Default remains inline | Task 1 |
| Materials toolbar 下载 button | Task 2 |
| No embed / no new materials API | (out of scope — not implemented) |
| api.md note | Task 3 |
| Auth/path errors unchanged | Task 1 (no change to those branches) |
