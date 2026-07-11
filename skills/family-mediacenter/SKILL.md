---
name: family-mediacenter
description: 通过本地 Family Media Center 服务下载音视频、管理播放列表，并生成 TVBox 多合一订阅（yt-dlp / aria2 / Alist / TVBox feed）
version: 1.4.0
author: family-mediacenter
tags: [download, yt-dlp, aria2, alist, 网盘, 音视频, 多媒体, 播放列表, TVBox, 直播]
trigger_keywords: [下载, 音视频, 网盘, yt-dlp, 磁力, 离线下载, 多媒体, 播放列表, 轮播, TVBox, 影视仓, 猫影视, 订阅, feed]
---

# Family Media Center Skill

通过本地 REST API 调用 Family Media Center 服务，统一下载音视频、HTTP 直链、磁力链接和网盘资源；管理多媒体播放列表；生成 TVBox 多合一订阅。

## 前置条件

1. Family Media Center 服务已启动（默认 `http://127.0.0.1:18026`）
2. 支持直接粘贴分享文案，服务会自动提取其中的链接
3. 对应引擎可用：
   - **yt-dlp**：YouTube、Bilibili、抖音等音视频站点
   - **aria2**：HTTP/HTTPS 直链、磁力链接
   - **Alist**：网盘分享链接（需在设置中启用并配置 Alist）

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
| YouTube / Bilibili / 抖音 / Twitter 等 | `ytdlp` 或留空自动 | 支持 `options.format`、`audio_only`、`subtitle` |
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
