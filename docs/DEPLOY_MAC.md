# macOS 生产环境部署指南

本文说明在 **Mac（Apple Silicon / Intel）** 上部署 **Family Media Center** 的完整流程：应用本身、下载组件、Docker 可选服务，以及 **launchd 常驻**。

统一入口：**`./service.sh`**（与 zip 解压后相同；源码仓库也可 `./install.sh`）。

## 支持情况概览

| 项目 | macOS 支持 | 说明 |
|------|------------|------|
| Family Media Center 主服务 | ✅ | `service.sh install` 自动 venv + launchd |
| yt-dlp | ✅ | `service.sh install` 已通过 pip 安装 |
| aria2 | ✅ | `brew install aria2` 或 Docker（推荐生产） |
| Alist | ✅ | Docker（`docker-compose.yml`） |
| 文件外链 `/files/` | ✅ | 与平台无关 |
| launchd 常驻 | ✅ | `service.sh install` 自动注册 |

---

## 一、环境要求

- macOS 12+（Monterey 或更高推荐）
- **Python 3.10+** — 系统自带 3.9.x 不可用
- 可选：**Homebrew**、**Docker Desktop**

> 若仅有 Python 3.9：`brew install python@3.12` 或从 [python.org](https://www.python.org/downloads/macos/) 安装，然后：
> `PYTHON_BIN=python3.12 ./service.sh install`

---

## 二、快速安装（推荐）

```bash
cd /path/to/family_mediacenter
chmod +x service.sh install.sh scripts/*.sh deploy/**/*.sh

# 安装 venv + 依赖 + launchd 开机自启（config.yaml 写入 host=0.0.0.0）
./service.sh install
# 或
./install.sh
```

浏览器访问：http://127.0.0.1:18026  
健康检查：`curl http://127.0.0.1:18026/health`  
组件状态：http://127.0.0.1:18026/components

**本地开发（热重载，仅 127.0.0.1）：**

```bash
./scripts/setup_venv.sh   # 首次
./scripts/dev.sh
```

---

## 三、服务维护

| 动作 | 命令 |
|------|------|
| 安装 + 自启 | `./service.sh install` |
| 重启 | `./service.sh restart --force` |
| 停止 | `./service.sh stop` |
| 状态 | `./service.sh status` |
| 卸载自启 | `./service.sh uninstall` |
| 诊断 | `./service.sh diagnose` |

日志：`logs/launchd.out.log`、`logs/launchd.err.log`

---

## 四、下载组件

### yt-dlp（必选）

`service.sh install` 已通过 pip 安装。若组件页仍不可用，在 **设置 → yt-dlp** 填写：

```text
/path/to/family_mediacenter/.venv/bin/yt-dlp
```

### aria2（可选）

```bash
brew install aria2
# 或
docker compose up -d aria2
```

`config.yaml` 中 `engines.aria2.secret` 与 `docker-compose.yml` 的 `RPC_SECRET` 一致。

### Alist（可选）

```bash
docker compose up -d alist
```

首次访问 http://127.0.0.1:5244，从容器日志获取管理员密码。

---

## 五、生产配置

`service.sh install` 默认写入 `server.host: 0.0.0.0`。可按需编辑 `config.yaml`：

```yaml
server:
  host: 0.0.0.0
  port: 18026
  api_key: "请设置强密钥"

files:
  public_base_url: "http://192.168.x.x:18026"
```

---

## 六、验证清单

| 检查项 | 命令 / 地址 |
|--------|-------------|
| 健康检查 | `curl http://127.0.0.1:18026/health` |
| 组件状态 | `/components` |
| 试下载 | 仪表盘粘贴视频链接 |
| API Key | 设置 Key 后无 Key 写操作应 401 |

---

## 七、常见问题

**Q: Python 3.9 / venv 版本过低？**

```bash
rm -rf .venv
PYTHON_BIN=python3.12 ./service.sh install
```

**Q: macOS 12 不要用 brew 装 yt-dlp**

使用 venv 内 pip 安装的 yt-dlp（install 已包含）。

**Q: 其他设备无法访问？**

确认 `config.yaml` 中 `host: 0.0.0.0`，并检查防火墙是否放行 18026。

**Q: aria2 RPC 无法连接？**

确认 aria2 进程或 Docker 容器在运行，且 `rpc_url`、`secret` 正确。

---

## 八、打包部署

开发机打 zip（接入门户安装升级）：

```bash
./scripts/build_and_pack.sh
```

产物：`dist_out/family_mediacenter.zip`，解压后同样使用 `./service.sh install`。

详见 [deploy/INSTALL.txt](../deploy/INSTALL.txt)。
