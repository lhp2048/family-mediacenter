# 电子书分享书架 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 发布一个目录或一本电子书的分享链接。目录打开是书架，点书再阅读；单本打开就是阅读页。

**Architecture:** 一张 `material_shares` 表记录 token、相对书库根的路径和是否目录。公开页只通过分享接口列目录和读文件，路径必须落在分享根里面。阅读器沿用 `material_reader.js`，但文件地址换成分享文件接口。管理端电子图书页负责发布、复制、重置和停止。

**Tech Stack:** FastAPI、SQLAlchemy async、SQLite、现有 Alpine 电子书页与 `material_reader.js`。

## Global Constraints

- 书架页 `/shelf/{token}`，阅读 `/shelf/{token}/read?path=`，单本 `/book/{token}`
- 子文件夹可进入，不能超出分享根，不能回到整个书库
- 分享响应和阅读器不得出现 `/files/`
- 支持 `.md` `.pdf` `.epub` `.txt`；`meta.json` 和点开头的文件不进列表
- 同一路径最多一条分享；再次发布沿用 token，重置才换 token
- 写接口在配置了 API 密钥时要求 `X-API-Key`；公开页和读文件不要求
- 不做观看统计、设备允许、分享页下载
- 规格：`docs/superpowers/specs/2026-11-05-ebook-share-design.md`

## File structure

- Create: `app/models/material_share.py` — ORM 与响应模型
- Create: `app/services/material_share.py` — 发布、路径约束、列目录、读文件
- Create: `app/api/material_share.py` — 管理接口与公开 JSON
- Create: `app/web/templates/shelf.html` — 书架页
- Create: `app/web/templates/shelf_read.html` — 分享阅读页（书架返回或单本）
- Modify: `app/db.py` — `create_all` 导入新表
- Modify: `app/main.py` — 挂上路由
- Modify: `app/api/web.py` — `/shelf/{token}`、`/shelf/{token}/read`、`/book/{token}`
- Modify: `app/web/templates/materials.html` — 发布 / 复制 / 重置 / 停止
- Modify: `app/web/static/material_reader.js` — 只在已传入 `public_url` 时使用它（分享页传入分享文件地址）
- Test: `scripts/test_material_share.py`
- Modify: `skills/family-mediacenter/SKILL.md`、`skills/family-mediacenter/references/api.md`

---

### Task 1: 分享记录与路径约束

**Files:**
- Create: `app/models/material_share.py`
- Create: `app/services/material_share.py`
- Modify: `app/db.py`
- Test: `scripts/test_material_share.py`

**Produces:**

- `MaterialShareORM`
- `material_share_service.enable(sub_path, public_base) -> MaterialShareResponse`
- `disable(sub_path)`、`rotate(sub_path, public_base)`
- `resolve_share(token) -> MaterialShareORM`，未启用或不存在则 `ValueError("分享不存在或已停用")`
- `contain_path(share_sub_path, requested) -> str`，返回规范化后的相对路径；越界则 `ValueError("路径超出分享范围")`

- [ ] **Step 1: 写失败测试**

`scripts/test_material_share.py` 在临时书库目录里放 `故事/甲.txt` 和 `故事/下一层/乙.txt`。断言：

- 发布目录 `故事` 得到 `/shelf/{token}`，`is_dir` 为真
- 再次发布同一路径，token 不变
- `contain_path("故事", "下一层/乙.txt")` 得到 `故事/下一层/乙.txt`
- `contain_path("故事", "../其他.txt")` 抛出「路径超出分享范围」
- 发布文件 `故事/甲.txt` 得到 `/book/{token}`
- 停止后 `resolve_share` 抛出「分享不存在或已停用」

运行：`family-mediacenter/.venv/bin/python family-mediacenter/scripts/test_material_share.py`  
Expected: FAIL，模块不存在。

- [ ] **Step 2: 实现模型与服务**

`sub_path` 唯一。`token` 用 `secrets.token_urlsafe(16)`。路径规范化复用 `material_service._normalize_materials_subpath`，再用 `Path.resolve()` 确认落在书库根内，并且等于分享根或以其为前缀。目录分享要求目标是目录，单本要求是支持的电子书文件。

`db.init_db` 增加 `from app.models.material_share import MaterialShareORM`。

- [ ] **Step 3: 测试通过**

同一命令 Expected: `OK: material share`

---

### Task 2: 公开列表与文件接口

**Files:**
- Create: `app/api/material_share.py`
- Modify: `app/main.py`
- Modify: `app/services/material_share.py`
- Test: `scripts/test_material_share.py`

**Produces:**

- `GET /api/v1/shelf/{token}?path=` 返回书架名、`meta.json` 的 title/description/author、面包屑、条目。条目的 `file_url` 形如 `/api/v1/shelf/{token}/file?path=`
- `GET /api/v1/shelf/{token}/file?path=` 与 `GET /api/v1/book/{token}/file` 返回 `FileResponse`，支持 Range
- `GET /api/v1/book/{token}` 返回书名、kind、`file_url`
- `POST /api/v1/materials/share`、`DELETE /api/v1/materials/share`、`POST /api/v1/materials/share/rotate`，body `{ "sub_path": "..." }`，依赖 `verify_api_key`

- [ ] **Step 1: 扩展测试**

用 `TestClient`：

- 书架 JSON 含 `甲.txt` 与文件夹 `下一层`，不含 `meta.json`，不含 `/files/`
- `path=下一层` 只看到 `乙.txt`
- `path=../` 返回 400
- 文件接口内容与磁盘一致；单本文件接口同样可读
- 停止分享后书架与文件接口为 404

Expected: FAIL，路由不存在。

- [ ] **Step 2: 实现**

列表复用 `browse_materials` 的目录扫描规则，但把 `public_url` 换成分享文件地址，响应里去掉书库绝对路径。封面若在分享目录内，改写到同一个 file 接口。`main.py` 挂上 `material_share_router`。

- [ ] **Step 3: 测试通过**

Expected: `OK: material share`

---

### Task 3: 书架页与阅读页

**Files:**
- Create: `app/web/templates/shelf.html`
- Create: `app/web/templates/shelf_read.html`
- Modify: `app/api/web.py`
- Modify: `app/web/static/material_reader.js` 仅当调用方需要传入自定义文件地址时

**Produces:** 两个公开 HTML 页。

- [ ] **Step 1: 页面测试**

`TestClient`：

- `GET /shelf/{token}` 为 200，正文含书架名和「甲」
- `GET /shelf/{token}/read?path=甲.txt` 为 200，含返回书架的链接，阅读器配置的文件地址是分享 file 接口
- `GET /book/{file_token}` 为 200，不含「返回书架」
- 分享关闭后两个页面都是 404

- [ ] **Step 2: 模板**

`shelf.html`：顶栏书架名；有简介和作者则显示；封面网格；面包屑第一级是书架名。点文件夹改 `?path=`，点书跳到 `/shelf/{token}/read?path=`。手机单列。

`shelf_read.html`：复用 `materials_embed.html` 的阅读器结构。`fileInfo.public_url` 设成分享文件地址，`material_reader.js` 继续读这个字段。从书架进入时显示「返回书架」，`href` 回到进入前的目录层。单本页不渲染该链接。

`web.py` 三个路由在分享无效时 404，文案「分享不存在或已停用」。

- [ ] **Step 3: 测试通过**

Expected: `OK: material share`

---

### Task 4: 管理端发布

**Files:**
- Modify: `app/web/templates/materials.html`
- Modify: `skills/family-mediacenter/SKILL.md`
- Modify: `skills/family-mediacenter/references/api.md`

- [ ] 在目录预览和选中文件的工具栏增加：未分享时「发布分享」；已分享时「复制链接」「重置链接」「停止分享」。当前目录用 `currentPath`，选中的书用 `selectedEntry.sub_path`。
- [ ] 发布成功后把链接放进可复制的地址框。停止前沿用现有 `uiConfirm`。
- [ ] 技能说明补上三个管理接口和两个公开页面。写明分享地址不依赖 `/files/` 外链开关。
- [ ] 再跑 `scripts/test_material_share.py` 与 `scripts/test_playlist_share.py`，两者都打印 OK。

## Self-review

- 规格里的书架、阅读、单本、路径约束、一路径一条分享、管理端四动作、不做统计，都落在 Task 1–4。
- 公开文件地址统一为 `/api/v1/shelf|book/{token}/file`，测试禁止响应里出现 `/files/`。
- 不新增设备允许和观看统计。
