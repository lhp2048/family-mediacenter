# E-Book Source File Download — Design

**Date:** 2026-07-27  
**Status:** Approved  
**Scope:** Family Media Center materials (电子书) Web UI

## Goal

Allow users to download the original e-book source file (`.md` / `.pdf` / `.epub` / `.txt`) from the materials library page, with a forced browser save (Content-Disposition: attachment) and the original filename.

## Non-Goals

- Download button in `/materials/embed` reader toolbar
- Dedicated materials download API for Flutter / other clients
- Folder ZIP download
- Changing default inline preview behavior of `/files/...`

## Approach

Extend existing public file serving: `GET /files/{file_path}?download=1`.

Reuse path safety, `files.public_access` / API key checks, and streaming behavior. Do not add a parallel materials-only download route.

## Backend

**File:** `app/api/files.py` — `serve_public_file`

| Query | Behavior |
|-------|----------|
| `download` absent / `0` / `false` / empty | `content_disposition_type="inline"` (current) |
| `download=1` / `true` | `content_disposition_type="attachment"`; filename = safe basename of the resolved file |

Error responses unchanged:

- Path outside downloads / missing file → 404
- `public_access=false` without valid API key → existing auth failure

## Frontend

**File:** `app/web/templates/materials.html`

- When a **file** is selected, show a **下载** button in the preview pane toolbar next to 「新窗口」 and 「复制文件链接」.
- Style: `small secondary` (match siblings).
- On click: navigate/trigger download using the entry’s `public_url` with `download=1` appended (use `&` if the URL already has a query string). Prefer an `<a download>` with `entry.name` so the suggested filename is the original name.
- Do not interrupt the embed reader iframe.

## Documentation

Update `skills/family-mediacenter/references/api.md` to note that `GET /files/{path}?download=1` forces download of the source file.

## Testing

Manual checks:

1. Select pdf / epub / md / txt → 下载 → browser saves with correct name and extension.
2. Open same file without `download` → online reader / inline still works.
3. With `public_access` off and no key → download rejected same as other `/files/` access.

## Components

| Unit | Responsibility |
|------|----------------|
| `serve_public_file` | Toggle disposition via `download` query |
| materials preview toolbar | Expose download affordance for selected file |
| api.md | Document the query flag |
