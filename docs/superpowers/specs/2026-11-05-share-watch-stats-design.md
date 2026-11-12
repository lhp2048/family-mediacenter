# 分享页观看统计与设备允许

Date: 2026-11-05  
Product: family-mediacenter  
Status: approved

## Goal

分享页按设备记录观看时长、作息和内容热点，供 API 与 AI 查询。设备可被单独关闭播放，新设备默认允许。

## Identity

- 长期 cookie `fmc_visitor` 代表一台设备，同时保存最近 IP、原始 User-Agent 和短设备名（如 `iPad · Safari`）。
- 打开 `/watch/{token}` 成功时新建一条访问，cookie `fmc_visit` 指向这一次打开。
- 不做孩子命名。查询结果按设备分开，由人自行区分。
- 只统计分享页里的实际播放。管理页预览和 TVBox 的 `/files/` 不计入。

## Recording

播放器上报 `POST /api/v1/watch/{token}/stats`：

- `play`：该条目从「没在播」进入播放时加一次。暂停后再继续不加。
- `tick`：`delta_sec` 在 `(0, 15]` 时计入观看时长，并落到服务器本地时间的日期和小时。超出范围不加时长。
- `complete`：播到结束加一次。

同一次访问、同一条目、同一小时只更新一行。条目标题在写入时留快照。

## Query

`GET /api/v1/share/stats?from=YYYY-MM-DD&to=YYYY-MM-DD` 需要 `X-API-Key`（服务配置了密钥时）。缺省日期为最近 7 天（含今天）。

每台在范围内出现过的设备返回：`id`、`device_label`、`last_ip`、`user_agent`、`allowed`、`watch_sec`、按天的作息（当天时长、最早开始、最晚仍在看、各小时秒数）、按观看时长排序的热点条目（播放次数、播完次数）。

访问记录和播放明细只保留最近一个月：早于「上个月同一天」的行会在服务启动、打开分享页或查询统计时删除。设备记录和 `allowed` 不因过期删除。

## Access

`allowed` 默认 `true`。`PUT /api/v1/share/devices/{id}`，请求体 `{ "allowed": false }`，需要 API 密钥。

关闭后，该设备不能看分享视频，也不能看分享图书。分享播放页不返回节目和播放地址，页面显示「这台设备未允许播放」。分享书架和阅读页显示「这台设备未允许」，书的文件返回 403。播放地址为 `/api/v1/watch/{token}/media/{item_id}`，每次请求检查这台设备。`/files/` 外链保持原样。管理页里的图书预览不检查这个开关。被拒绝的设备仍出现在统计中。清除站点数据后会出现新设备，新设备默认允许。

允许按设备生效，不按播放列表分开。

## AI

MCP 工具 `share_watch_stats(from_date, to_date)` 与 `set_share_device_access(device_id, allowed)` 调用上述接口。AI 只根据返回的设备信息区分观看者，不自行把某台设备说成某个孩子。
