---
name: family-mediacenter
description: 通过本地 Family Media Center 服务下载音视频、上传本机电子书和音视频、管理播放列表，并生成 TVBox 多合一订阅（yt-dlp / aria2 / Alist / TVBox feed）
version: 1.6.0
author: family-mediacenter
tags: [download, yt-dlp, aria2, alist, 网盘, 音视频, 多媒体, 播放列表, 电子书, TVBox, 直播]
trigger_keywords: [下载, 上传, 音视频, 网盘, yt-dlp, 磁力, 离线下载, 多媒体, 播放列表, 电子书, 轮播, TVBox, 影视仓, 猫影视, 订阅, feed]
---

# Family Media Center Skill

通过本地 REST API 调用 Family Media Center 服务，统一下载音视频、HTTP 直链、磁力链接和网盘资源；管理多媒体播放列表；生成 TVBox 多合一订阅。

## 前置条件

1. Family Media Center 服务已启动（默认 `http://127.0.0.1:18026`）
2. 支持直接粘贴分享文案，服务会自动提取其中的链接
3. 对应引擎可用：
   - **yt-dlp**：YouTube、Bilibili、抖音等音视频站点；组件页可安装/检查更新/更新
   - **aria2**：HTTP/HTTPS 直链、磁力链接；组件页可启停本机 RPC 进程
   - **Alist**：网盘分享链接（需在设置中启用并配置 Alist）
   - **ffmpeg**：手动转 H.264+AAC 兼容 mp4；组件页可安装/更新（brew/scoop）

健康检查：`GET http://127.0.0.1:18026/health`

响应含 `service`、`version`（打包版本，如 `26.627.1551`）、`port`、各引擎可用状态。

若配置了 API Key，写操作及任务/文件/TVBox 源管理类 API 需携带请求头：`X-API-Key: <your-key>`

**局域网 / TVBox 访问**：`config.yaml` 中 `server.host` 设为 `0.0.0.0`；`files.public_base_url` 设为电视可访问的局域网地址（如 `http://192.168.1.10:18026`），勿用 `127.0.0.1`。

## 工作流程

1. **创建下载任务**
   ```http
   POST /api/v1/downloads
   Content-Type: application/json

   {
     "url": "https://www.bilibili.com/video/BV1xx",
     "engine": "ytdlp",
     "options": { "audio_only": false },
     "output_dir": "downloads/multimedia"
   }
   ```

2. **轮询任务状态**（每 2–5 秒）
   ```http
   GET /api/v1/tasks/{id}
   ```

3. **任务完成**：`status` 为 `completed` 时，从响应的 `file_path` 获取本地文件路径。

4. **失败处理**：`status` 为 `failed` 时，查看 `error_message`；检查 `/health` 确认引擎状态。

## 引擎选择指南

| 场景 | engine | 说明 |
|------|--------|------|
| YouTube / Bilibili / 抖音 / Twitter 等 | `ytdlp` 或留空自动 | 支持 `options.format`、`audio_only`、`subtitle`。B 站、抖音可在设置页扫码登录，Cookie 分别写入 `data/bilibili_cookies.txt`、`data/douyin_cookies.txt`，下载对应站点时自动使用。抖音扫码需要本机 Google Chrome |
| HTTP/HTTPS 直链 | `aria2` | 需 aria2 RPC 可用 |
| 磁力链接 `magnet:` | `aria2` | 需 aria2 支持 BT |
| Alist 分享链接 | `alist` | 需 Alist 已启用 |
| Alist 内部路径 | `alist` + `options.alist_path` | 如 `alist:///path/to/file` |

## options 示例

```json
{
  "audio_only": true,
  "format": "bestvideo+bestaudio",
  "subtitle": true,
  "cookies_file": "D:/cookies.txt",
  "alist_path": "/阿里云盘/视频.mp4",
  "offline_to_alist": false
}
```

## 管理任务

- 暂停：`POST /api/v1/tasks/{id}/pause`
- 取消：`POST /api/v1/tasks/{id}/cancel`
- 删除：`DELETE /api/v1/tasks/{id}?delete_file=false`
- 列表（全量，兼容旧用法）：`GET /api/v1/tasks?status=running`
- 列表（分页）：`GET /api/v1/tasks?page=1&page_size=15&tab=active`
- 计数：`GET /api/v1/tasks/counts`

列表条目较多时请加 `page` / `page_size`（默认每页 15 条），响应为 `{ items, total, page, page_size, total_pages }`；不传 `page` 时仍返回任务数组。

## 文件浏览（需 API Key）

下载目录文件管理（与 Web「文件」页一致）：

```http
GET /api/v1/files?path=&page=1&page_size=15
DELETE /api/v1/files?path=relative/path.mp4
```

公开访问文件（播放列表 `public_url` 使用此路径）：

```http
GET /files/{rel_path}
```

当 `files.public_access=false` 时需 API Key。

## WebDAV（可选）

在设置页启用 WebDAV 后，可用独立账号挂载整个 `downloads/`（含 `multimedia/`、`ebooks/`）。**保存后需重启服务**。

```yaml
webdav:
  enabled: true
  username: "webdav"
  password: "your-password"
  read_only: true   # false 允许上传/删除/重命名
```

连接地址：`http://127.0.0.1:18026/dav/`（Basic Auth）。适用于 Infuse、Finder、nPlayer 等。

## 多媒体中心 / 播放列表

下载完成的**视频/音频**会自动加入默认播放列表「全部下载」。也可创建自定义列表供轮播或 TVBox 直播频道。

### 查询（免 API Key）

```http
GET /api/v1/playlists
GET /api/v1/playlists/default/items
GET /api/v1/playlists/{id}/items?page=1&page_size=15
GET /api/v1/playlists/{id}/live.m3u
GET /api/v1/media/files?page=1&page_size=15
```

条目中的 `public_url` 可直接用于 `<video>` / 外部播放器。**一个播放列表 = TVBox 一个直播频道**；频道地址为 `live.m3u`，内含列表内所有可播媒体的 M3U 条目。

### MCP（按名称管理）

Cursor 里可直接说列表名和文件名，不必先查数字 ID：

- `list_playlist_items(playlist_name)`：查看某个列表
- `create_playlist(name)`：创建空列表
- `create_playlist_by_filename(playlist_name, filename)`：按文件名收录；同名列表已存在则只补新文件
- `remove_file_from_playlist(playlist_name, filename)`：从列表移除，不删磁盘文件
- `move_file_to_playlist(filename, playlist_name, from_playlist)`：改到另一个列表
- `delete_playlist_by_name(name)`：删除自定义列表

文件名写完整名，或只能对上一个文件的一部分。对上多个时不改动，并返回候选路径。通配符 `*` 一次处理全部匹配。

### 独立分享播放页

在多媒体中心可「发布分享页」，得到公开 URL：`/watch/{token}`（可停用/重置）。

- 简易播放器 + 完整标题列表；管理端可拖拽排序
- 每个列表一份全局播放进度与自动播放开关
- API：`GET /api/v1/watch/{token}`、`PUT .../progress`、`PUT .../autoplay`
- 播放地址是 `/api/v1/watch/{token}/media/{item_id}`，按打开页面的设备校验
- 若编码不被设备支持（如 HEVC），分享页仅提示到「多媒体」手动「转兼容」；不公开调写接口

### 分享页观看统计

每台打开分享页的设备单独统计观看时长、作息（按天、按小时）和内容热点。系统不保存孩子名字，用设备名和 IP 区分是谁。

```
GET /api/v1/share/stats?from=YYYY-MM-DD&to=YYYY-MM-DD
PUT /api/v1/share/devices/{id}
{ "allowed": false }
```

需要 API Key（若已配置）。不传日期时为最近 7 天。播放记录只保留最近一个月（从上个月的同一天算起），更早的访问和观看明细会删除；设备本身以及是否允许仍保留。新设备默认允许；`allowed: false` 后该设备不能再看分享视频，也不能再看分享图书，但仍出现在统计里。

MCP：`share_watch_stats(from_date, to_date)`、`set_share_device_access(device_id, allowed)`、`get_share_eye_care()`、`set_share_eye_care(enabled, play_minutes, rest_minutes)`、`share_eye_care_status()`、`reset_share_eye_care(device_id)`。只根据接口里的设备信息回答，不要把某台设备说成某个孩子，除非用户自己说明。

播放列表里的单个文件可以临时隐藏。`PUT /api/v1/playlists/{id}/items/{item_id}/share-hide`，请求体 `{ "hidden": true }`。隐藏后分享页和该列表的电视直播源当天都不展示、也不能播放。已经打开的分享页会在下次刷新时停掉这一条。第二天自动恢复；`hidden: false` 立即恢复。不删除磁盘文件。MCP：`set_playlist_item_share_hide(playlist_id, item_id, hidden)`。`list_playlist_items` 的条目带 `share_hidden`。

分享页可以按设备隐藏当天已经看完的条目。`PUT /api/v1/playlists/{id}/share/hide-completed`，请求体 `{ "enabled": false, "after": 1 }`。默认关闭；打开后默认完播 1 次就从这台设备的列表里隐藏，其他设备不受影响，第二天重新出现。后台在播放列表的「说明与分享」里设置。

护眼默认打开。同一台设备看视频和读电子书合在一起计时，连续满 30 分钟后要休息 15 分钟，休息期间不能继续看或读。其他设备不受影响。中间停下的时间达到休息时长，会重新计时。

```
GET /api/v1/share/eye-care
PUT /api/v1/share/eye-care
{ "enabled": true, "play_minutes": 30, "rest_minutes": 15 }
```

`play_minutes` 为 1–240，`rest_minutes` 为 1–180。后台在播放列表的「说明与分享」里也能改。

```
GET  /api/v1/share/eye-care/status
POST /api/v1/share/eye-care/devices/{id}/reset
```

`status` 需要 API Key（若已配置）。返回当前开关、时长，以及每台设备的 `locked`、`rest_remaining_sec`、`watched_sec`。`reset` 解除这一台的休息并清掉本轮已用时长，其他设备和开关不变。

### 电子书分享

在电子图书页可以把一个目录或一本书发成链接。目录是书架 `/shelf/{token}`，点书再读。单本是 `/book/{token}`。子文件夹可以进入，但不能走出这次分享的目录。

```
POST   /api/v1/materials/share
DELETE /api/v1/materials/share
POST   /api/v1/materials/share/rotate
```

请求体 `{ "sub_path": "故事" }`。需要 API Key（若已配置）。阅读地址不依赖文件外链。停掉分享或目标被删除后，旧链接失效。

### 电子书库管理

写操作需要 API Key（若已配置）。路径都相对书库根目录，不能超出书库。支持 `.pdf` `.epub` `.txt` `.md`。

```
POST /api/v1/materials/upload
multipart: file=<书.pdf>, sub_path=故事

POST /api/v1/materials/import
{ "url": "https://example.com/book.pdf", "sub_path": "故事", "filename": "书名.pdf" }

POST /api/v1/materials/folders
{ "path": "故事/新目录" }

POST /api/v1/materials/rename
{ "path": "故事/甲.txt", "name": "乙.txt" }

POST /api/v1/materials/move
{ "path": "甲.txt", "dest": "故事" }

DELETE /api/v1/materials?path=故事/甲.txt
```

`upload` 直接接收电子书文件，存进 `sub_path` 目录，电子图书页有「上传电子书」按钮。单文件最大 8 GiB，同名会拒绝。

音视频用 `POST /api/v1/playlists/{id}/upload`，multipart 字段名 `file`。文件进入多媒体目录并加入这个播放列表。多媒体页有「上传音视频」按钮。格式为常见音视频扩展名。

`import` 只接受 http/https 直链，强制 aria2，文件名不加 `task_` 前缀。`sub_path` 必须是已有目录。返回下载任务，用 `GET /api/v1/tasks/{id}` 看进度。同名文件会拒绝。

改名、移动会把命中的分享改到新路径，原来的链接仍然有效。删除文件或目录会停用命中的分享。不能改名、移动或删除书库根目录。

书架可以重命名：`POST /api/v1/materials/rename`，请求体 `{ "path": "旧书架", "name": "新书架" }`。分享链接不变，记录里的路径会跟着更新。MCP：`rename_ebook`。

播放列表可以重命名：`PUT /api/v1/playlists/{id}`，请求体 `{ "name": "新名称" }`。只改显示名称，分享链接和开关不变。默认列表也能改名，不能因此被删除。MCP：`rename_playlist(playlist_id, name)`。

MCP：`list_ebooks`、`import_ebook`、`upload_ebook`、`upload_media`、`create_ebook_folder`、`rename_ebook`、`move_ebook`、`delete_ebook`。

`upload_ebook(file_path, sub_path)` 上传这台电脑上的电子书。`upload_media(file_path, playlist_name, playlist_id)` 上传音视频。`playlist_id` 优先；只给名称时按名称匹配；都不传则进入默认列表。文件路径必须是媒体中心这台机器上的路径。

### 电子书阅读统计

分享阅读页按设备记录阅读时长、作息和打开过的书。设备和视频共用，允许开关也共用。只统计 `/shelf/{token}/read` 和 `/book/{token}`，书架列表和管理页预览不记。关掉的设备打不开分享书架和书。

```
GET /api/v1/share/read-stats?from=YYYY-MM-DD&to=YYYY-MM-DD
```

需要 API Key（若已配置）。不传日期时为最近 7 天。阅读记录只保留最近一个月。每台设备返回 `read_sec`、按天按小时的作息，以及 `hot_books`（书库路径、文件名、阅读秒数、打开次数）。

MCP：`share_read_stats(from_date, to_date)`。只根据接口里的设备信息回答，不要把某台设备说成某个孩子，除非用户自己说明。

### 兼容转码（ffmpeg）

设备播不了时，在多媒体中心点「转兼容」（需 API Key）：

```
POST /api/v1/convert
{ "item_id": 12, "playlist_id": 1 }
```

产出同目录 `原名_compat.mp4`，保留原片；所有引用该 `rel_path` 的播放列表条目会切到新文件。轮询 `GET /api/v1/convert/{job_id}`。

### 管理（需 API Key，若已配置）

```http
POST /api/v1/playlists
Body: { "name": "晚间轮播" }

POST /api/v1/playlists/{id}/items
Body: { "rel_path": "video.mp4" }
或: { "task_id": 3 }

POST /api/v1/playlists/{id}/reload
POST /api/v1/playlists/default/reload

DELETE /api/v1/playlists/{id}
DELETE /api/v1/playlists/{id}/items/{item_id}
```

### 典型场景

| 用户意图 | 操作 |
|----------|------|
| 查看可轮播内容 | `GET /api/v1/playlists/default/items` |
| 列表很多时分页浏览 | 上述接口加 `?page=1&page_size=15` |
| 创建专题列表 | `POST /api/v1/playlists` → `POST .../items` |
| 把刚下载的视频加入列表 | `POST .../items` + `task_id` 或 `rel_path` |
| 浏览下载目录中的媒体 | `GET /api/v1/media/files` |
| 磁盘与列表不同步 | `POST /api/v1/playlists/default/reload` |
| 获取单个列表的 TVBox 频道地址 | `GET /api/v1/playlists/{id}/live.m3u` |

Web 管理页：`/media` · 文件：`/files`

## TVBox 源管理与订阅

MediaCenter 可聚合多个 TVBox 配置源，并自动把**非空播放列表**并入直播分组。

### 用户如何在 TVBox 里订阅

1. 浏览器打开 **`/tvbox`**，复制页顶「多合一订阅」地址，形如：
   ```
   http://192.168.1.10:18026/api/v1/tvbox/feed.json
   ```
2. 在 TVBox / 影视仓 / 猫影视 → **设置 → 配置地址**，粘贴并保存。
3. 点播：来自已启用的外部 TVBox 源（多仓 `urls`）。
4. 直播 → **家庭播放列表**：每个播放列表对应一个频道（`live.m3u`）。

电视必须与 MediaCenter 同网段，且 `files.public_base_url` 配置正确。

### 查询（feed 默认公开）

```http
GET /api/v1/tvbox/feed.json
GET /api/v1/tvbox/feed-info
GET /api/v1/tvbox/sources
GET /api/v1/tvbox/overview
GET /api/v1/tvbox/sidecar/status
GET /api/v1/tvbox/sources/{id}/reports/latest
```

`feed.json` 合并内容：

- **点播**：所有 `enabled=true` 且非直播类的源 → `urls[]`（`{ "name", "url" }`）
- **直播（外部）**：URL 为 `.m3u/.m3u8/.txt` 或备注含「直播」→ `lives[].channels[]`
- **直播（播放列表）**：每个非空播放列表 → 一个 `lives` 分组；组内一条频道，URL 为 `live.m3u`（组合该列表全部可播放条目）

### 管理（需 API Key）

```http
POST /api/v1/tvbox/sources
Body: { "name": "源名称", "url": "https://...", "enabled": true, "note": "" }

PUT /api/v1/tvbox/sources/{id}
Body: { "enabled": false }

DELETE /api/v1/tvbox/sources/{id}

POST /api/v1/tvbox/sources/reorder
Body: [{ "id": 1, "sort_order": 0 }, { "id": 2, "sort_order": 1 }]

POST /api/v1/tvbox/sources/{id}/test?mode=quick|full
POST /api/v1/tvbox/sources/test-all?mode=quick|full
POST /api/v1/tvbox/schedule/run
```

源测试为分层探测（L1 可达 → L2 格式 → L3–L7 CMS/Spider/直播等）。多仓源会递进抽样子配置，直到找到可用子源；根配置可用但子源全挂时标为 **partial**。

### 典型场景

| 用户意图 | 操作 |
|----------|------|
| 获取 TVBox 配置地址 | `GET /api/v1/tvbox/feed-info` 或 Web `/tvbox` |
| 添加社区源 | `POST /api/v1/tvbox/sources` |
| 测试源是否可用 | `POST /api/v1/tvbox/sources/{id}/test` |
| 调整 feed 里源顺序 | `POST /api/v1/tvbox/sources/reorder`（Web 拖拽亦可） |
| 把播放列表给 TV 看 | 确保 `feed_include_playlists: true`，或单独用 `live.m3u` |
| 关闭播放列表进 feed | `config.yaml` → `tvbox.feed_include_playlists: false` |

Web 管理页：`/tvbox`

### 相关配置（config.yaml）

```yaml
tvbox:
  public_feed: true
  feed_title: "Family Media Center TVBox 多合一"
  feed_include_playlists: true
  feed_playlist_group: "家庭播放列表"
  test_timeout: 15
  test_probe_children: 3
  spider_sidecar_enabled: true
  spider_sidecar_url: "http://127.0.0.1:9978"
```

## 错误处理

| 错误 | 处理 |
|------|------|
| Engine not available | 检查 `/health`，安装或启动对应工具 |
| Alist is not enabled | 在 Web 设置页启用 Alist 并配置 URL/Token |
| 401 Invalid API key | 添加 `X-API-Key` 请求头 |
| 连接失败 | 确认服务运行在 18026 |
| TVBox 加载 feed 失败 | 检查 `host: 0.0.0.0`、防火墙、`public_base_url` |
| 播放列表频道无内容 | 列表需有媒体文件；`files.public_access: true` |

## Skill 安装

服务运行时可从在线端点安装到 WorkBuddy：

```bash
curl -fsSL http://127.0.0.1:18026/scripts/install-workbuddy-skill.sh | bash -s -- http://127.0.0.1:18026
```

详细 API 见 `references/api.md`。
