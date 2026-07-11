#!/usr/bin/env bash
# macOS: install Family Media Center as launchd user service
set -euo pipefail

LABEL="com.family.smart.mediacenter"
LEGACY_LABELS=("com.family.mediacenter.service")
_set_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${_set_dir}/lib/paths.sh" ]]; then
  # shellcheck source=lib/paths.sh
  source "${_set_dir}/lib/paths.sh"
else
  # shellcheck source=../lib/paths.sh
  source "${_set_dir}/../lib/paths.sh"
fi
mediacenter_init_paths || exit 1
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

DO_UNINSTALL=0
DO_STATUS=0
PORT="18026"
BIND="0.0.0.0"

usage() {
  sed -n '2,4p' "$0" | sed 's/^# \{0,1\}//'
}

launchctl_user_domain() {
  echo "gui/$(id -u)"
}

launchctl_load() {
  local domain
  domain="$(launchctl_user_domain)"
  if launchctl print "${domain}/${LABEL}" &>/dev/null; then
    launchctl bootout "${domain}" "${PLIST_DEST}" 2>/dev/null || true
  fi
  launchctl bootstrap "${domain}" "${PLIST_DEST}"
  launchctl kickstart -k "${domain}/${LABEL}" 2>/dev/null || true
}

launchctl_unload() {
  local domain
  domain="$(launchctl_user_domain)"
  launchctl bootout "${domain}" "${PLIST_DEST}" 2>/dev/null || true
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --uninstall) DO_UNINSTALL=1; shift ;;
    --status)    DO_STATUS=1; shift ;;
    --port)      PORT="${2:-18026}"; shift 2 ;;
    --bind)      BIND="${2:-0.0.0.0}"; shift 2 ;;
    -h|--help)   usage; exit 0 ;;
    *) echo "未知参数: $1" >&2; usage; exit 1 ;;
  esac
done

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "错误: 此脚本仅适用于 macOS" >&2
  exit 1
fi

PYTHON="${APP_ROOT}/.venv/bin/python"

if [[ "${DO_STATUS}" -eq 1 ]]; then
  domain="$(launchctl_user_domain)"
  echo "应用目录: ${APP_ROOT}"
  echo "Plist: ${PLIST_DEST}"
  [[ -f "${PLIST_DEST}" ]] && echo "已安装: 是" || echo "已安装: 否"
  if launchctl print "${domain}/${LABEL}" &>/dev/null; then
    launchctl print "${domain}/${LABEL}" | sed -n '1,25p'
  else
    echo "运行状态: 未加载"
  fi
  [[ -x "${PYTHON}" ]] && echo "venv: $("${PYTHON}" --version 2>&1)" || echo "venv: 未就绪"
  if declare -F show_listen_check >/dev/null; then
    show_listen_check "${PORT}"
  fi
  exit 0
fi

if [[ "${DO_UNINSTALL}" -eq 1 ]]; then
  launchctl_unload
  rm -f "${PLIST_DEST}"
  if declare -F kill_port_listeners >/dev/null; then
    kill_port_listeners "${PORT}"
  fi
  echo "已卸载 ${LABEL}"
  exit 0
fi

if [[ ! -f "${APP_ROOT}/pyproject.toml" ]]; then
  echo "错误: 请在安装目录内执行" >&2
  exit 1
fi

chmod +x "${SCRIPT_DIR}/run_service.sh" "${SCRIPT_DIR}/start_service_mac.sh" \
  "${SCRIPT_DIR}/restart_service_mac.sh" "${SCRIPT_DIR}/stop_service_mac.sh" 2>/dev/null || true

mediacenter_setup_venv "${APP_ROOT}" || exit 1
PYTHON="${APP_ROOT}/.venv/bin/python"
patch_config_server "${APP_ROOT}" "${BIND}" "${PORT}" "${PYTHON}" || exit 1
ensure_runtime_dirs "${APP_ROOT}"

if declare -F kill_port_listeners >/dev/null; then
  kill_port_listeners "${PORT}"
fi

if declare -F remove_legacy_launchd_labels >/dev/null; then
  remove_legacy_launchd_labels "${LEGACY_LABELS[@]}"
fi

mkdir -p "${LOG_DIR}" "${HOME}/Library/LaunchAgents"
: > "${LOG_DIR}/launchd.out.log"
: > "${LOG_DIR}/launchd.err.log"

cat > "${PLIST_DEST}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON}</string>
        <string>-m</string>
        <string>app.main</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${APP_ROOT}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/launchd.out.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/launchd.err.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin</string>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
        <key>PYTHONUTF8</key>
        <string>1</string>
    </dict>
</dict>
</plist>
EOF

echo "==> 注册 launchd 服务"
launchctl_load

if wait_for_health "${PORT}"; then
  echo "本机访问正常: http://127.0.0.1:${PORT}/"
else
  echo "错误: 服务未在端口 ${PORT} 响应 /health" >&2
  if declare -F show_service_logs >/dev/null; then
    show_service_logs "${LOG_DIR}"
  fi
  exit 1
fi

if declare -F print_access_urls >/dev/null; then
  print_access_urls "${PORT}" "${BIND}"
fi
if declare -F verify_lan_access >/dev/null; then
  verify_lan_access "${PORT}" "${BIND}" || true
fi
