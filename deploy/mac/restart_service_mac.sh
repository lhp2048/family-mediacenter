#!/usr/bin/env bash
set -euo pipefail

LABEL="com.family.smart.mediacenter"
_set_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${_set_dir}/lib/paths.sh" ]]; then
  source "${_set_dir}/lib/paths.sh"
else
  source "${_set_dir}/../lib/paths.sh"
fi
mediacenter_init_paths || exit 1
RUN_SCRIPT="${SCRIPT_DIR}/run_service.sh"
PLIST_DEST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
LOG_DIR="${APP_ROOT}/logs"

if [[ -f "${LIB_DIR}/service_common.sh" ]]; then
  # shellcheck source=lib/service_common.sh
  source "${LIB_DIR}/service_common.sh"
fi
if [[ -f "${LIB_DIR}/resolve_python.sh" ]]; then
  # shellcheck source=lib/resolve_python.sh
  source "${LIB_DIR}/resolve_python.sh"
fi

PORT="18026"
DO_FORCE=0

launchctl_user_domain() { echo "gui/$(id -u)"; }

is_port_listening() {
  if _lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
    return 0
  fi
  mediacenter_health_ok "${PORT}"
}

kill_port() {
  if declare -F kill_port_listeners >/dev/null; then
    kill_port_listeners "${PORT}"
    return 0
  fi
  local pids
  pids="$(_lsof -ti tcp:"${PORT}" 2>/dev/null || true)"
  [[ -n "${pids}" ]] && kill ${pids} 2>/dev/null || true
}

restart_launchd() {
  local domain
  domain="$(launchctl_user_domain)"
  [[ ! -f "${PLIST_DEST}" ]] && return 1
  if ! launchctl print "${domain}/${LABEL}" &>/dev/null; then
    launchctl bootstrap "${domain}" "${PLIST_DEST}"
  fi
  launchctl kickstart -k "${domain}/${LABEL}" 2>/dev/null || launchctl bootstrap "${domain}" "${PLIST_DEST}"
  return 0
}

start_background() {
  mkdir -p "${LOG_DIR}"
  chmod +x "${RUN_SCRIPT}" 2>/dev/null || true
  nohup bash "${RUN_SCRIPT}" >> "${LOG_DIR}/launchd.out.log" 2>> "${LOG_DIR}/launchd.err.log" &
  disown $! 2>/dev/null || true
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --force) DO_FORCE=1; shift ;;
    --port)  PORT="${2:-18026}"; shift 2 ;;
    *) shift ;;
  esac
done

[[ ! -f "${APP_ROOT}/pyproject.toml" ]] && { echo "错误: 未找到 pyproject.toml" >&2; exit 1; }

if [[ "${DO_FORCE}" -eq 0 ]] && is_port_listening; then
  echo "服务已在运行: http://127.0.0.1:${PORT}/"
  exit 0
fi

if [[ "${DO_FORCE}" -eq 1 ]]; then kill_port; fi

if [[ -f "${PLIST_DEST}" ]]; then
  restart_launchd || true
  sleep 2
fi

if ! is_port_listening; then
  echo "launchd 未监听端口，改用后台 run_service.sh 启动"
  kill_port
  start_background
  sleep 2
fi

if wait_for_health "${PORT}"; then
  echo "OK: http://127.0.0.1:${PORT}/"
else
  echo "ERROR: 启动失败，/health 无响应" >&2
  if declare -F show_service_logs >/dev/null; then
    show_service_logs "${LOG_DIR}"
  fi
  exit 1
fi
