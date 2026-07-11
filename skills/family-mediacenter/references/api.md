# Family Media Center API Reference

Base URL: `http://127.0.0.1:18026`

## Authentication

Optional. When `api_key` is set in settings, protected endpoints require:

```
X-API-Key: your-api-key
```

**Public (no key):** `GET /health`, playlist read endpoints (`GET /api/v1/playlists*`, `GET /api/v1/playlists/{id}/live.m3u`), `GET /api/v1/media/files` (read), `GET /files/...` when `files.public_access=true`, `GET /api/v1/materials`, `GET /materials/embed`, `GET /api/v1/tvbox/feed.json` when `tvbox.public_feed=true`, `GET /api/v1/tvbox/sources` (read), `GET /api/v1/tvbox/feed-info`, `GET /api/v1/tvbox/overview`, `GET /api/v1/tvbox/sources/{id}/reports/latest`, `GET /api/v1/tvbox/sources/{id}/reports/history`, `GET /api/v1/tvbox/sidecar/status`, `GET /api/v1/tvbox/schedule/status`.

**Protected:** downloads, tasks, settings, engines, file list/delete, playlist writes, TVBox source writes/tests/schedule trigger.

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
    "alist": false
  },
  "engines_available": 1,
  "engines_total": 3
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
```

Used by playlist `public_url`. Requires API key when `files.public_access=false`.

### Get Settings

```
GET /api/v1/settings
```

### Engine Status

```
GET /api/v1/engines
GET /api/v1/engines/{name}
POST /api/v1/engines/{name}/test
```

`name`: `ytdlp` | `aria2` | `alist`

Returns download directory, concurrency, and detailed status for each engine.

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
    "aria2": { "rpc_url": "http://127.0.0.1:6800/jsonrpc", "secret": "" },
    "alist": { "enabled": true, "url": "http://127.0.0.1:5244", "token": "" }
  },
  "files": { "public_access": true },
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

### Embed reader (iframe for Flutter Web)

```
GET /materials/embed?path={sub_path}
```

`path` is the file's `sub_path` from browse API. Returns a minimal HTML page with in-browser PDF/EPUB/Markdown/TXT preview.

Reader toolbar (embed page):

- **翻页 / 滚动**（默认翻页）：PDF 翻页仅渲染当前页；滚动模式按视口 IntersectionObserver 按需渲染各页；PDF/EPUB 通过 URL 流式加载（支持 HTTP Range）
- **缩放**：− / + / 重置；放大后可鼠标拖动平移
- Markdown / TXT：全文一次加载；翻页模式按视口高度虚拟分页（不重复请求）

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
| `list_playlist_items` | Items in default or specified playlist (full list, no pagination param) |
| `list_media_files` | Media files in download directory (full list) |
| `create_playlist` | Create playlist by name |
| `delete_playlist` | Delete custom playlist |
| `add_playlist_item` | Add by `rel_path` or `task_id` |
| `remove_playlist_item` | Remove item from playlist |

For large playlists, prefer REST API with `page` / `page_size`, or call `list_tasks` with `page`.
