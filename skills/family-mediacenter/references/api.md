# Family Media Center API Reference

Base URL: `http://127.0.0.1:18026`

## Authentication

Optional. When `api_key` is set in settings, protected endpoints require:

```
X-API-Key: your-api-key
```

**Public (no key):** `GET /health`, playlist read endpoints (`GET /api/v1/playlists*`, `GET /api/v1/playlists/{id}/live.m3u`), `GET /watch/{token}`, `GET /api/v1/watch/{token}`, `GET /api/v1/watch/{token}/media/{item_id}`, `POST /api/v1/watch/{token}/stats`, `PUT /api/v1/watch/{token}/progress`, `PUT /api/v1/watch/{token}/autoplay`, `POST /api/v1/share/read/{token}/stats`, `GET /api/v1/media/files` (read), `GET /files/...` when `files.public_access=true`, `GET /api/v1/materials`, `GET /materials/embed`, `GET /shelf/{token}`, `GET /book/{token}`, `GET /api/v1/shelf/{token}`, `GET /api/v1/shelf/{token}/file`, `GET /api/v1/book/{token}`, `GET /api/v1/book/{token}/file`, `GET /api/v1/tvbox/feed.json` when `tvbox.public_feed=true`, `GET /api/v1/tvbox/sources` (read), `GET /api/v1/tvbox/feed-info`, `GET /api/v1/tvbox/overview`, `GET /api/v1/tvbox/sources/{id}/reports/latest`, `GET /api/v1/tvbox/sources/{id}/reports/history`, `GET /api/v1/tvbox/sidecar/status`, `GET /api/v1/tvbox/schedule/status`.

**Protected:** downloads, tasks, settings, engines, engine lifecycle actions, convert, file list/delete, playlist writes, `GET /api/v1/share/stats`, `GET /api/v1/share/read-stats`, `PUT /api/v1/share/devices/{id}`, material share publish/rotate/stop (`POST|DELETE /api/v1/materials/share`, `POST /api/v1/materials/share/rotate`, `GET /api/v1/materials/share`), ebook library writes (`POST /api/v1/materials/import`, `POST /api/v1/materials/upload`, `POST /api/v1/materials/folders`, `POST /api/v1/materials/rename`, `POST /api/v1/materials/move`, `DELETE /api/v1/materials`), playlist media upload (`POST /api/v1/playlists/{id}/upload`), TVBox source writes/tests/schedule trigger.

## Pagination

Several list endpoints support optional pagination. Default page size: **15** (max **100**).

| Query | Type | Description |
|-------|------|-------------|
| `page` | int ≥ 1 | When present, response is paginated |
| `page_size` | int 1–100 | Items per page (default 15) |

**Paginated response:**

```json
{
  "items": [ /* ... */ ],
  "total": 42,
  "page": 1,
  "page_size": 15,
  "total_pages": 3
}
```

**Backward compatible:** omit `page` → returns a plain array (tasks) or full list (playlists/media).

Endpoints with pagination: `GET /api/v1/tasks`, `GET /api/v1/files`, `GET /api/v1/playlists/{id}/items`, `GET /api/v1/media/files`.

---

## Endpoints

### Health Check

```
GET /health
```

Response:

```json
{
  "status": "ok",
  "service": "family_mediacenter",
  "version": "26.627.1551",
  "port": 18026,
  "engines": {
    "ytdlp": true,
    "aria2": false,
    "alist": false,
    "ffmpeg": true
  },
  "engines_available": 2,
  "engines_total": 4
}
```

`version` comes from `family-product.json` at install root (`dev` in development).

### Create Download

```
POST /api/v1/downloads
```

Body:

```json
{
  "url": "string (required)",
  "engine": "ytdlp | aria2 | alist (optional)",
  "options": {},
  "output_dir": "optional absolute path"
}
```

Response: Task object.

### List Tasks

```
GET /api/v1/tasks?status=running
GET /api/v1/tasks?tab=active|completed|failed|all
GET /api/v1/tasks?page=1&page_size=15&tab=active
GET /api/v1/tasks?page=2&status=completed
```

- `tab`: Web dashboard grouping (`active` = pending/running/paused)
- With `page`: paginated object; without `page`: array of tasks

### Task Counts

```
GET /api/v1/tasks/counts
```

Response example:

```json
{
  "active": 2,
  "completed": 10,
  "failed": 1,
  "all": 13
}
```

### Delete Task

```
DELETE /api/v1/tasks/{id}?delete_file=false
```

Only for completed / failed / cancelled tasks. `delete_file=true` also removes the downloaded file.

### Get Task

```
GET /api/v1/tasks/{id}
```

### Pause Task

```
POST /api/v1/tasks/{id}/pause
```

### Cancel Task

```
POST /api/v1/tasks/{id}/cancel
```

### List Files (download directory)

```
GET /api/v1/files?path=&page=1&page_size=15
```

`path`: relative subdirectory under `downloads/multimedia` (empty = root).

Response includes `items` (files/dirs with `name`, `path`, `size`, `is_dir`, `public_url`), plus `total`, `page`, `total_pages`, `path`, `parent`.

### Delete File

```
DELETE /api/v1/files?path=relative/path.mp4
```

Also removes matching playlist entries.

### Serve File (public URL)

```
GET /files/{file_path}
GET /files/{file_path}?download=1
```

Used by playlist `public_url` and materials `public_url`. Requires API key when `files.public_access=false`.

- Default: `Content-Disposition: inline` (browser preview / streaming).
- `download=1` or `download=true`: `Content-Disposition: attachment` with the source filename (force save).

### WebDAV (optional)

Mount the whole `downloads/` tree at `/dav/` (Basic Auth). Configure under settings `webdav`:

```json
{
  "webdav": {
    "enabled": true,
    "username": "webdav",
    "password": "secret",
    "read_only": true
  }
}
```

- Requires restart after enabling/changing credentials or `read_only`.
- Default `read_only: true`; set `false` to allow PUT/DELETE/MOVE/MKCOL.
- URL: `http://<host>:18026/dav/`

### Get Settings

```
GET /api/v1/settings
```

Returns `webdav` alongside `server`, `download`, `files`, `engines`, etc.

### Engine Status

```
GET /api/v1/engines
GET /api/v1/engines/{name}
POST /api/v1/engines/{name}/test
```

`name`: `ytdlp` | `aria2` | `alist` | `ffmpeg`

Returns download directory, concurrency, and detailed status for each engine.

### Engine lifecycle actions

Manage **yt-dlp** / **ffmpeg** (install, check update, update, refresh) and **aria2** / **alist** process control.

`engines.aria2.runtime` / `engines.alist.runtime`: `local` (default) | `docker` | `remote`.

| Mode | start/stop/restart |
|------|--------------------|
| `local` | local binary |
| `docker` | `docker start/stop/restart` using `container_name` |
| `remote` | rejected (detect only) |

| Engine | Actions |
|--------|---------|
| `aria2` | `start`, `stop`, `restart`, `check_update` |
| `alist` | `start`, `stop`, `restart`, `check_update`（无自动安装） |

```
POST /api/v1/engines/{name}/actions
GET  /api/v1/engines/actions/{job_id}
```

Requires API Key. Body:

```json
{ "action": "install | check_update | update | restart | start | stop" }
```

| Engine | Actions |
|--------|---------|
| `ytdlp` | `install`, `check_update`, `update`, `restart` (refresh status) |
| `ffmpeg` | same as ytdlp (brew/scoop; else returns install help) |
| `aria2` | `start`, `stop`, `restart`, `check_update`（受 `runtime` 约束） |
| `alist` | `start`, `stop`, `restart`, `check_update`（受 `runtime` 约束；无自动安装） |

Poll job until `status` is `completed` or `failed`. Same `(engine, action)` while running returns the existing job.

### Site login cookies

Bilibili and Douyin QR login each write their own Netscape cookie file. Downloads for that site use it ahead of the shared `engines.ytdlp.cookies_file`.

```
GET  /api/v1/bilibili/login/status
POST /api/v1/bilibili/qr/start
GET  /api/v1/bilibili/qr/poll?session_id=

GET  /api/v1/douyin/login/status
POST /api/v1/douyin/qr/start
GET  /api/v1/douyin/qr/poll?session_id=
```

`qr/start` returns `session_id` plus a QR `url` (Douyin returns `qrcode_base64` from the official login page opened in local Google Chrome). Poll until `status` is `success`, `expired`, or `error`. `POST /api/v1/douyin/qr/cancel?session_id=` closes that Chrome session. Success stores `data/bilibili_cookies.txt` or `data/douyin_cookies.txt`. Douyin login does not replace the shared cookie path.

### Compat convert (ffmpeg)

Manual H.264+AAC remux for devices that cannot play HEVC/etc. Keeps the original file; writes `stem_compat.mp4` beside it and updates all playlist items that referenced the old `rel_path`.

```
POST /api/v1/convert
GET /api/v1/convert/{job_id}
```

Requires API Key. Body (either `rel_path` or `item_id`):

```json
{
  "rel_path": "video.mkv",
  "playlist_id": 1,
  "item_id": 12
}
```

Response (job; poll until `completed` / `failed` / `skipped`):

```json
{
  "id": "a1b2c3d4e5f6",
  "status": "pending",
  "message": "排队中",
  "source": "video.mkv",
  "output": "",
  "public_url": "",
  "ok": false
}
```

Share watch page does **not** call this API; it only hints to convert from Media Center UI.

### Update Settings

```
PUT /api/v1/settings
```

Body (partial):

```json
{
  "download": { "default_dir": "downloads/multimedia", "max_concurrent": 3 },
  "engines": {
    "ytdlp_path": "yt-dlp",
    "ffmpeg_path": "ffmpeg",
    "aria2": { "rpc_url": "http://127.0.0.1:6800/jsonrpc", "secret": "" },
    "alist": { "enabled": true, "url": "http://127.0.0.1:5244", "token": "" }
  },
  "files": { "public_access": true },
  "webdav": {
    "enabled": false,
    "username": "",
    "password": "",
    "read_only": true
  },
  "tvbox": {
    "public_feed": true,
    "feed_title": "Family Media Center TVBox 多合一",
    "feed_include_playlists": true,
    "feed_playlist_group": "家庭播放列表"
  }
}
```

---

## Task Object

```json
{
  "id": 1,
  "url": "https://...",
  "title": "filename",
  "source_type": "ytdlp",
  "status": "running",
  "progress": 45.5,
  "speed": "1.2MiB/s",
  "file_path": "<项目目录>/downloads/multimedia/task_1_video.mp4",
  "file_size": 1048576,
  "engine_task_id": "abc123",
  "options": {},
  "output_dir": "<项目目录>/downloads/multimedia",
  "error_message": "",
  "created_at": "2026-06-14T10:00:00",
  "updated_at": "2026-06-14T10:01:00"
}
```

## Status Values

`pending` | `running` | `completed` | `failed` | `paused` | `cancelled`

---

## TVBox Sources & Feed

Manage third-party TVBox config URLs and expose a merged subscription for TVBox / 影视仓 / 猫影视 clients.

### Merged Feed (for TVBox「配置地址」)

```
GET /api/v1/tvbox/feed.json
```

Public when `tvbox.public_feed=true` (default). Returns TVBox-compatible JSON:

```json
{
  "urls": [
    { "name": "示例点播源", "url": "https://example.com/vod.json" }
  ],
  "lives": [
    {
      "group": "Family Media Center TVBox 多合一",
      "channels": [
        { "name": "IPTV 源", "url": "https://example.com/live.m3u" }
      ]
    },
    {
      "group": "全部下载",
      "channels": [
        {
          "name": "全部下载",
          "url": "http://192.168.1.10:18026/api/v1/playlists/1/live.m3u"
        }
      ]
    }
  ]
}
```

- **urls**: enabled non-live sources (multi-warehouse VOD), ordered by `sort_order`; each item is `{ "name", "url" }`
- **lives**: external live sources + optional playlist groups
- **One playlist = one live group + one combined channel** (`live.m3u` lists all playable items)

Use LAN IP in URLs for TV clients; configure `files.public_base_url`.

### Feed Info

```
GET /api/v1/tvbox/feed-info
```

Response:

```json
{
  "feed_url": "http://127.0.0.1:18026/api/v1/tvbox/feed.json",
  "source_count": 5,
  "enabled_count": 3,
  "title": "Family Media Center TVBox 多合一"
}
```

### List Sources

```
GET /api/v1/tvbox/sources
```

Returns all sources with compact `last_test_detail.summary` (full detail via reports API).

### Create Source

```
POST /api/v1/tvbox/sources
```

Body:

```json
{
  "name": "社区源",
  "url": "https://example.com/tvbox.json",
  "enabled": true,
  "note": ""
}
```

Notes containing `直播` or URLs ending in `.m3u`/`.m3u8`/`.txt` are classified as live sources in the feed.

### Update / Delete / Reorder

```
PUT /api/v1/tvbox/sources/{id}
DELETE /api/v1/tvbox/sources/{id}
POST /api/v1/tvbox/sources/reorder
Body: [{ "id": 1, "sort_order": 0 }, { "id": 2, "sort_order": 1 }]
```

### Test Sources

Layered probe: L1 reachability → L2 JSON/M3U parse → L3–L7 CMS/Spider/live sampling.

```
POST /api/v1/tvbox/sources/{id}/test?mode=quick|full
POST /api/v1/tvbox/sources/test-all?mode=quick|full
```

Multi-warehouse configs: probes child URLs in batches; continues until an OK child is found or all are exhausted. Root OK with zero child OK → **partial** (not fail).

### Reports & Overview

```
GET /api/v1/tvbox/sources/{id}/reports/latest
GET /api/v1/tvbox/sources/{id}/reports/history?limit=30
GET /api/v1/tvbox/overview
GET /api/v1/tvbox/sidecar/status
GET /api/v1/tvbox/schedule/status
POST /api/v1/tvbox/schedule/run
```

### TVBox config keys (`config.yaml`)

| Key | Default | Description |
|-----|---------|-------------|
| `public_feed` | `true` | Allow unauthenticated `feed.json` |
| `feed_title` | 多合一 title | Live group name for external live sources |
| `feed_include_playlists` | `true` | Add non-empty playlists as live groups |
| `feed_playlist_group` | `家庭播放列表` | *(legacy, ignored)* — playlist name is used as group name |
| `test_probe_children` | `3` | Initial batch size for multi-warehouse child probe |
| `spider_sidecar_enabled` | `true` | Enable Java Spider sidecar for L4+ |

Web UI: `/tvbox`

---

## Playlists (Multimedia Center)

Read endpoints are **public** (no API key). Write endpoints require `X-API-Key` when configured.

### List Playlists

```
GET /api/v1/playlists
```

### Default Playlist

```
GET /api/v1/playlists/default
GET /api/v1/playlists/default/items
GET /api/v1/playlists/default/items?page=1&page_size=15
```

Default playlist auto-collects completed video/audio downloads.

### Playlist Items (for carousel / rotation)

```
GET /api/v1/playlists/{id}/items
GET /api/v1/playlists/{id}/items?page=1&page_size=15
```

Each item includes `public_url` for direct playback:

```json
{
  "id": 1,
  "playlist_id": 1,
  "rel_path": "video.mp4",
  "title": "My Video",
  "name": "video.mp4",
  "size": 1048576,
  "media_type": "video",
  "task_id": 3,
  "sort_order": 1,
  "public_url": "http://127.0.0.1:18026/files/video.mp4",
  "exists": true,
  "added_at": "2026-06-14T10:00:00"
}
```

### Playlist Live M3U (TVBox channel)

One playlist maps to **one** TVBox live channel. The M3U lists all playable items (`exists=true`) with direct `public_url` entries.

```
GET /api/v1/playlists/{id}/live.m3u
```

Response: `application/vnd.apple.mpegurl`

```m3u
#EXTM3U
#EXTINF:-1,My Video
http://192.168.1.10:18026/files/video.mp4
```

Also included in `feed.json` when `tvbox.feed_include_playlists=true`: each playlist with playable items becomes a `lives` group.

Web UI shows copyable channel URL at `/media` when a playlist is selected.

Rename a playlist. Only the display name changes. The share token, share URL, and share switch stay as they are. The default playlist can be renamed.

```
PUT /api/v1/playlists/{id}
{ "name": "新名称" }
```

### Playlist share watch page

```
POST   /api/v1/playlists/{id}/share
DELETE /api/v1/playlists/{id}/share
POST   /api/v1/playlists/{id}/share/rotate
DELETE /api/v1/playlists/{id}/share/progress
PUT    /api/v1/playlists/{id}/share/autoplay
PUT    /api/v1/playlists/{id}/share/hide-completed
PUT    /api/v1/playlists/{id}/items/{item_id}/share-hide
PUT    /api/v1/playlists/{id}/items/reorder
GET    /watch/{token}
GET    /api/v1/watch/{token}
GET    /api/v1/watch/{token}/media/{item_id}
POST   /api/v1/watch/{token}/stats
PUT    /api/v1/watch/{token}/progress
PUT    /api/v1/watch/{token}/autoplay
GET    /api/v1/share/stats?from=YYYY-MM-DD&to=YYYY-MM-DD
PUT    /api/v1/share/devices/{id}
GET    /api/v1/share/eye-care
PUT    /api/v1/share/eye-care
GET    /api/v1/share/eye-care/status
POST   /api/v1/share/eye-care/devices/{id}/reset
```

Public HTML player with full titles, auto-next, global progress/autoplay per playlist. Reorder: `[{ "id", "sort_order" }, ...]`.

Share playback uses `/api/v1/watch/{token}/media/{item_id}` and checks the device cookie. New devices are allowed. `PUT /api/v1/share/devices/{id}` with `{ "allowed": false }` blocks that device from shared video and shared books. `/files/` is unchanged. The admin materials preview is not checked.

`PUT /api/v1/playlists/{id}/items/{item_id}/share-hide` body: `{ "hidden": true }`. Hides that file from the share page list, the playlist live M3U, and blocks share playback for the server's local date. An already open share page drops the file on its next refresh. The next local day shows and plays it again. `{ "hidden": false }` clears it immediately. The file stays on disk and in the admin playlist. The response includes `share_hidden` and `share_hidden_on` (`YYYY-MM-DD` while hidden today, otherwise empty). Unknown items return 404.

`PUT /api/v1/playlists/{id}/share/hide-completed` body: `{ "enabled": false, "after": 1 }`. Default off, `after` defaults to 1 (1–99). When enabled, a device that has finished an item that many times today (server local date, existing complete events) no longer sees it in the share list. Other devices are unchanged. The next local day shows it again.

`GET` and `PUT /api/v1/share/eye-care` body: `{ "enabled": true, "play_minutes": 30, "rest_minutes": 15 }`. Default on. `play_minutes` is 1–240 and `rest_minutes` is 1–180. Each device accumulates video playback and ebook reading together. At the limit, that device must wait out the rest before any share page will play or open a book again. A pause at least as long as the rest clears the streak. Other devices are unchanged.

`GET /api/v1/share/eye-care/status` requires the API key when one is configured. It returns the same policy plus `devices`: `id`, `device_label`, `last_ip`, `user_agent`, `allowed`, `locked`, `rest_remaining_sec`, `watched_sec`. `POST /api/v1/share/eye-care/devices/{id}/reset` clears that device's rest and current streak. Unknown ids return 404.

`GET /api/v1/share/stats` requires the API key when one is configured. Omit dates for the last 7 local days. Stored visits and playback rows older than one calendar month (before the same day last month) are deleted. Device rows and their `allowed` flag are kept. Each device includes `device_label`, `last_ip`, `user_agent`, `allowed`, `watch_sec`, `by_day` (hours and first/last play) and `hot_items`.

`POST /api/v1/watch/{token}/stats` body: `{ "type": "play"|"tick"|"complete", "item_id": 1, "delta_sec": 5 }`. A tick counts only when `0 < delta_sec <= 15`.

### Ebook share reading stats

```
GET  /api/v1/share/read-stats?from=YYYY-MM-DD&to=YYYY-MM-DD
POST /api/v1/share/read/{token}/stats
```

`GET` requires the API key when one is configured. Omit dates for the last 7 local days. Rows older than one calendar month are deleted with the same cutoff as watch stats. Device rows and `allowed` stay. `allowed: false` also blocks the shelf, the reader, and book file bytes. A denied device sees「这台设备未允许」 and file requests return 403.

Only `/shelf/{token}/read` and `/book/{token}` record a visit. The shelf list and `/materials/embed` do not. The reader sends `open` once per visit while the page is visible, and `tick` with `0 < delta_sec <= 15`. Books are grouped by library path. Each device includes `read_sec`, `by_day`, and `hot_books` (`path`, `title`, `read_sec`, `open_count`).

### List Media Files in Download Directory

```
GET /api/v1/media/files
GET /api/v1/media/files?page=1&page_size=15
```

Returns media file entries (same shape as playlist items). Without `page`, returns full array.

### Create Playlist

```
POST /api/v1/playlists
Body: { "name": "My List" }
```

### Delete Playlist

```
DELETE /api/v1/playlists/{id}
```

Cannot delete the default playlist.

### Upload a local audio or video file

Multipart form. Field name is `file`. The file is saved into the multimedia directory and added to this playlist. Same-name files are rejected. Maximum size is 8 GiB. Extensions: `.mp4` `.mkv` `.webm` `.mov` `.avi` `.flv` `.m4v` `.mp3` `.m4a` `.flac` `.wav` `.aac` `.ogg` `.opus`.

```
POST /api/v1/playlists/{id}/upload
Content-Type: multipart/form-data
```

The page for this is **多媒体 → 上传音视频**.

### Add Item

```
POST /api/v1/playlists/{id}/items
Body: { "rel_path": "subdir/video.mp4" }
或: { "task_id": 1 }
```

### Remove Item

```
DELETE /api/v1/playlists/{id}/items/{item_id}
```

### Reload from Disk

Scan the download directory and sync the playlist (add new media files, remove entries whose files were deleted). Does not modify download tasks.

```
POST /api/v1/playlists/{id}/reload
POST /api/v1/playlists/default/reload
```

Response:

```json
{
  "added": 2,
  "removed": 1,
  "item_count": 5,
  "message": "新增 2 个、移除 1 个"
}
```

---

## Materials (E-Book Library)

Browse the configured e-book directory (`materials.dir`, default `ebooks` under project `downloads/`). Video downloads use `download.default_dir` (`downloads/multimedia`). Supports `.md`, `.pdf`, `.epub`, `.txt`. Optional `meta.json` per folder.

### Service discovery (Family Smart Apps / Portal)

1. Configure portal root: `http://<host>:18024`
2. `GET /api/v1/portal/services` → read `services.mediacenter.apiBaseUrl` and `origin`
3. Call materials API directly on mediacenter (CORS enabled for LAN Web clients)

### Browse materials

```
GET /api/v1/materials?path=&page=1&page_size=15
```

| Query | Description |
|-------|-------------|
| `path` | Sub-path relative to materials root (empty = root) |
| `page` | Page number (default 1) |
| `page_size` | Items per page (default 15, max 100) |

Response:

```json
{
  "root": "/path/to/downloads/ebooks",
  "dir": "ebooks",
  "path": "",
  "parent": "",
  "folder": {
    "title": "",
    "description": "",
    "author": "",
    "tags": [],
    "cover_url": ""
  },
  "entries": [
    {
      "name": "sample.epub",
      "sub_path": "sample.epub",
      "rel_path": "ebooks/sample.epub",
      "is_dir": false,
      "kind": "epub",
      "size": 1048576,
      "modified_at": "2026-07-04T12:00:00",
      "public_url": "http://127.0.0.1:18026/files/ebooks/sample.epub"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 15,
  "total_pages": 1
}
```

To download the source file from the Web UI or clients, append `?download=1` to `public_url` (same `/files/...` endpoint).

### Manage the library

Writes need the API key when one is configured. `path` is relative to the materials root and cannot leave it. Supported book extensions are `.pdf`, `.epub`, `.txt`, `.md`.

```
POST /api/v1/materials/import
{ "url": "https://example.com/book.pdf", "sub_path": "故事", "filename": "书名.pdf" }

POST /api/v1/materials/upload
Content-Type: multipart/form-data
file=<book.pdf>
sub_path=故事

POST /api/v1/materials/folders
{ "path": "故事/新目录" }

POST /api/v1/materials/rename
{ "path": "故事/甲.txt", "name": "乙.txt" }

POST /api/v1/materials/move
{ "path": "甲.txt", "dest": "故事" }

DELETE /api/v1/materials?path=故事/甲.txt
```

`upload` is a multipart form (`file`, optional `sub_path`) used by the 电子图书 page. It stores the book in that folder immediately. Maximum size is 8 GiB. Same-name files are rejected. The response is `{ "path", "name", "is_dir" }`.

`import` accepts only an `http` or `https` direct file URL. `sub_path` must already be a directory (`""` is the library root). `filename` is optional when the URL path already ends with a supported extension. The call forces aria2, keeps the book filename (no `task_` prefix), and returns the same task object as `POST /api/v1/downloads`. Poll `GET /api/v1/tasks/{id}`. A file that already exists is rejected.

`folders` creates the directory and any missing parents. `rename` changes only the final name; a file must keep a supported extension. Existing share links keep the same token; stored paths are rewritten to the new name. `move` requires `dest` to be an existing directory. `DELETE` removes a file, or a directory and everything inside it. The library root cannot be renamed, moved, or deleted.

Rename and move rewrite matching share records onto the new path, so the existing token keeps working. Delete disables those shares; the old URL then fails.

Folder and rename/move responses: `{ "path", "name", "is_dir" }`. Delete: `{ "ok": true, "path" }`. Missing paths are 404. Name conflicts and an existing share on the destination are 409.

### Embed reader (iframe for Flutter Web)

```
GET /materials/embed?path={sub_path}
```

`path` is the file's `sub_path` from browse API. Returns a minimal HTML page with in-browser PDF/EPUB/Markdown/TXT preview.

Reader toolbar (embed page):

- **翻页 / 滚动**（默认翻页）：PDF 翻页仅渲染当前页；滚动模式按视口 IntersectionObserver 按需渲染各页；PDF/EPUB 通过 URL 流式加载（支持 HTTP Range）
- **缩放**：− / + / 重置；放大后可鼠标拖动平移
- Markdown / TXT：全文一次加载；翻页模式按视口高度虚拟分页（不重复请求）

### Share a folder or a book

One share per library path. Publish again reuses the token. Rotate replaces it. These writes need the API key when one is configured. Reading does not, and does not use `/files/`.

```
POST   /api/v1/materials/share
DELETE /api/v1/materials/share
POST   /api/v1/materials/share/rotate
GET    /api/v1/materials/share?sub_path=
```

Body for the three writes: `{ "sub_path": "故事" }`. Empty `sub_path` is the materials root. Response: `enabled`, `token`, `share_url`, `is_dir`, `sub_path`.

```
GET /shelf/{token}
GET /shelf/{token}?path=下一层
GET /shelf/{token}/read?path=甲.txt
GET /api/v1/shelf/{token}?path=
GET /api/v1/shelf/{token}/file?path=
GET /book/{token}
GET /api/v1/book/{token}
GET /api/v1/book/{token}/file
```

A directory share is a bookshelf. Subfolders stay inside that share. A file share opens the reader directly. Stop or delete the target and the old URL returns 404.

---

## Skill Distribution

| URL | Description |
|-----|-------------|
| `GET /skills/family-mediacenter/SKILL.md` | Skill markdown |
| `GET /skills/family-mediacenter/references/api.md` | This reference |
| `GET /skills/family-mediacenter/bundle.zip` | Skill zip bundle |
| `GET /scripts/install-workbuddy-skill.sh` | WorkBuddy install script |

---

## MCP Tools (Cursor)

Configure `mcp_server/server.py` with env `FAMILY_MEDIACENTER_URL`, optional `FAMILY_MEDIACENTER_API_KEY`.

| Tool | Description |
|------|-------------|
| `create_download` | Create download task (`url`, optional `engine`, `output_dir`, `options` JSON) |
| `get_task` | Task status by ID |
| `list_tasks` | List tasks; optional `status` filter; optional `page` (page_size=50) |
| `cancel_task` | Cancel task by ID |
| `get_download_settings` | Read service settings |
| `health_check` | Service health + engine availability |
| `list_playlists` | All playlists |
| `list_playlist_items` | 查看列表。`playlist_name` 按名称（可唯一部分匹配），或 `playlist_id`；都不传则默认列表 |
| `list_media_files` | Media files in download directory (full list) |
| `create_playlist` | 按名称创建空列表 |
| `create_playlist_by_filename` | 按文件名创建或复用列表，并加入匹配的音视频。逗号分隔多个条件，`*` 为通配 |
| `delete_playlist` | Delete custom playlist by id |
| `delete_playlist_by_name` | 按名称删除自定义列表。不能删除「全部下载」 |
| `add_playlist_item` | Add by `rel_path` or `task_id` |
| `remove_playlist_item` | Remove item by numeric id |
| `remove_file_from_playlist` | 按文件名从列表移除，不删磁盘文件。多名匹配时只返回候选 |
| `move_file_to_playlist` | 把文件改到目标列表。`from_playlist` 可指定来源；省略则从其他列表移出 |
| `share_watch_stats` | 分享页每台设备的观看时长、作息和热点。可选 `from_date` / `to_date`（YYYY-MM-DD） |
| `share_read_stats` | 分享阅读页每台设备的阅读时长、作息和打开过的书。可选 `from_date` / `to_date`（YYYY-MM-DD） |
| `list_ebooks` | 列出电子书库。`path` 为子目录，空为根目录 |
| `import_ebook` | 把 http/https 直链下到书库。`sub_path` 为目标目录，`filename` 可选 |
| `upload_ebook` | 上传本机电子书文件。`file_path` 为本机路径，`sub_path` 为书库目录 |
| `upload_media` | 上传本机音视频并加入播放列表。`playlist_id` 优先，否则 `playlist_name`，都不传则默认列表 |
| `create_ebook_folder` | 新建书库目录 |
| `rename_ebook` | 重命名书或目录，分享路径跟着改 |
| `move_ebook` | 移动到书库内另一个目录。`dest` 为空表示根目录 |
| `delete_ebook` | 删除书或目录，并停用命中的分享 |
| `set_share_device_access` | 允许或拒绝某台设备看分享视频和分享图书。`device_id` 来自统计，`allowed` 为 true/false |

For large playlists, prefer REST API with `page` / `page_size`, or call `list_tasks` with `page`.
