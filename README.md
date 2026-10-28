# Family Media Center

家庭统一下载与媒体管理服务（**:18026**）：集成 **yt-dlp**（音视频）、**aria2**（HTTP/磁力/BT）、**Alist**（网盘），提供 Web 后台、文件管理、多媒体播放列表，以及 WorkBuddy Skill / MCP 集成。

> GitHub 仓库 **[family-mediacenter](https://github.com/lhp2048/family-mediacenter)**；smart-family monorepo 内本地目录 **`family_mediacenter`**。Python 包名 `family_mediacenter`，CLI 命令 `family-mediacenter`。

## 功能概览

| 模块 | 说明 |
|------|------|
| **下载引擎** | yt-dlp、aria2、Alist 可插拔，自动路由站点 |
| **Web 仪表盘** | 粘贴链接或分享文案、任务 Tab、实时进度 |
| **组件状态** | 引擎可用性检测与健康检查 |
| **文件管理** | 浏览 `downloads/multimedia/`，外链 `/files/…`，删除与复制链接 |
| **多媒体中心** | 播放列表；默认列表自动收录完成的视频/音频 |
| **设置** | 分类折叠配置，含 yt-dlp / aria2 / Alist **安装帮助** |
| **REST API** | OpenAPI：`/docs` |
| **AI 集成** | WorkBuddy Skill + Cursor MCP |

## 环境要求

- Python **3.10+**
- 可选：Docker（aria2 + Alist）、Homebrew（macOS 安装引擎）

## 快速开始

### 1. 克隆与安装

```bash
git clone git@github.com:lhp2048/family-mediacenter.git
cd family-mediacenter
pip install -e .
pip install yt-dlp
# Cursor MCP（可选，会安装 mcp + cryptography）
pip install -e ".[mcp]"
```

### 2. 安装下载组件（可选）

| 组件 | 安装方式 |
|------|----------|
| yt-dlp | `pip install yt-dlp` 或 `brew install yt-dlp` |
| aria2 | `brew install aria2` / Scoop / **Docker**（推荐） |
| Alist | **Docker**（`docker compose up -d alist`） |

**macOS / Linux 一键安装服务**：`./service.sh install`（或 `./install.sh`）

设置页展开各引擎条目可查看分平台安装命令。生产部署见 [docs/DEPLOY_MAC.md](docs/DEPLOY_MAC.md) 与 [deploy/INSTALL.txt](deploy/INSTALL.txt)。

### 3. 配置

编辑 `config.yaml`（节选）：

```yaml
server:
  host: 127.0.0.1   # 局域网访问改为 0.0.0.0
  port: 18026
  api_key: ""       # 生产环境建议设置

download:
  default_dir: downloads/multimedia
  max_concurrent: 3

files:
  public_access: true
  public_base_url: ""

engines:
  ytdlp_path: yt-dlp
  ffmpeg_path: ffmpeg
  aria2:
    rpc_url: http://127.0.0.1:6800/jsonrpc
    secret: family-mediacenter   # 与 docker-compose 中 RPC_SECRET 一致
  alist:
    enabled: false
    url: http://127.0.0.1:5244
    token: ""
```

### 4. 启动

| 场景 | 命令 |
|------|------|
| **本地开发**（热重载） | `scripts\dev.bat` / `./scripts/dev.sh` |
| **安装 + 开机自启** | `service.bat install` / `./service.sh install` |
| **重启 / 停止** | `service.bat restart` / `./service.sh restart --force` · `service.bat stop` |
| **快捷安装** | `install.bat` / `./install.sh` |

首次请先初始化 venv：`scripts\setup_venv.bat` / `./scripts/setup_venv.sh`

访问：**http://127.0.0.1:18026**（开发默认仅本机；`service.sh install` 会写入 `0.0.0.0` 供局域网）

### 5. Docker（aria2 + Alist）

```bash
docker compose up -d
```

- aria2 RPC：`http://127.0.0.1:6800`，Secret：`family-mediacenter`
- Alist：http://127.0.0.1:5244（首次登录查看容器日志获取密码）

## Web 页面

| 路径 | 功能 |
|------|------|
| `/` | 下载任务仪表盘 |
| `/files` | 下载文件管理 |
| `/media` | 多媒体播放列表 |
| `/components` | 引擎组件状态 |
| `/settings` | 系统设置与安装帮助 |
| `/docs` | API 文档 |

## API 示例

```bash
# 创建下载（支持整段分享文案，自动提取 URL）
curl -X POST http://127.0.0.1:18026/api/v1/downloads \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.bilibili.com/video/BV1xx"}'

# 任务列表
curl http://127.0.0.1:18026/api/v1/tasks?tab=completed

# 默认播放列表（轮播，免 API Key）
curl http://127.0.0.1:18026/api/v1/playlists/default/items

# 文件外链
curl -O http://127.0.0.1:18026/files/your-video.mp4

# 健康检查
curl http://127.0.0.1:18026/health
```

配置了 `api_key` 时，写操作需请求头：`X-API-Key: <your-key>`

完整 API 见 `skills/family-mediacenter/references/api.md`。

## WorkBuddy Skill

```bash
mkdir -p ~/.workbuddy/skills
cp -r skills/family-mediacenter ~/.workbuddy/skills/family-mediacenter
```

支持下载任务与**播放列表管理**（见 `skills/family-mediacenter/SKILL.md`）。

## Cursor MCP

需先安装可选依赖：`pip install -e ".[mcp]"`

```json
{
  "mcpServers": {
    "family-media": {
      "command": "python",
      "args": ["/path/to/family-mediacenter/mcp_server/server.py"],
      "env": {
        "FAMILY_MEDIACENTER_URL": "http://127.0.0.1:18026",
        "FAMILY_MEDIACENTER_API_KEY": ""
      }
    }
  }
}
```

下载工具：`create_download`、`list_tasks`、`get_task`、`cancel_task` …

播放列表：`list_playlists`、`list_playlist_items`（可传列表名）、`create_playlist`、`create_playlist_by_filename`、`remove_file_from_playlist`、`move_file_to_playlist`、`delete_playlist_by_name`。文件名写完整名或唯一的一部分；通配符一次处理全部匹配。

## 项目结构

```
family-mediacenter/          # git clone 默认目录名
├── app/                 # FastAPI 应用
│   ├── engines/         # yt-dlp, aria2, alist
│   ├── services/        # 任务、文件、播放列表
│   ├── api/             # REST + Web 路由
│   └── web/             # 模板与静态资源
├── skills/family-mediacenter/ # WorkBuddy Skill
├── mcp_server/          # MCP Server
├── deploy/              # 安装部署（service/install + 各平台脚本）
├── scripts/             # 开发、打包、skill 安装
├── docs/DEPLOY_MAC.md   # macOS 生产部署
├── config.yaml
└── docker-compose.yml
```

## 许可证

MIT
