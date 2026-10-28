# Engine runtime modes (aria2 / Alist)

**Date:** 2026-09-19

## Goal

aria2 and Alist support selectable **runtime** modes. Default: **local process**.

| Mode | Meaning | Lifecycle |
|------|---------|-----------|
| `local` | Binary on same host | start / stop / restart |
| `docker` | Named container on same host | `docker start/stop/restart` |
| `remote` | Service elsewhere | detect only (start/stop/restart → 400) |

## Config

```yaml
engines:
  aria2:
    runtime: local   # local | docker | remote
    rpc_url: http://127.0.0.1:6800/jsonrpc
    secret: ""
    container_name: family-mediacenter-aria2
  alist:
    enabled: false
    runtime: local
    url: http://127.0.0.1:5244
    token: ""
    binary_path: ""   # optional; else PATH / common paths
    container_name: family-mediacenter-alist
```

## Implementation notes

- Alist local start: `alist server --port <from url>`
- Docker: require `docker` CLI; use configured `container_name`
- Status API exposes `runtime` + `process_control` (bool) for UI buttons
- Components page shows start/stop/restart when `process_control`
