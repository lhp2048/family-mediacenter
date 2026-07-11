#!/usr/bin/env bash
# macOS: stop launchd service or kill port listener
set -euo pipefail

LABEL="com.family.smart.mediacenter"
_set_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${_set_dir}/lib/paths.sh" ]]; then
  source "${_set_dir}/lib/paths.sh"
else
  source "${_set_dir}/../lib/paths.sh"
fi
mediacenter_init_paths || exit 1

if [[ -f "${LIB_DIR}/service_common.sh" ]]; then
  # shellcheck source=lib/service_common.sh
  source "${LIB_DIR}/service_common.sh"
fi

PLIST_DEST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
PORT="${PORT:-18026}"

launchctl_user_domain() {
  echo "gui/$(id -u)"
}

domain="$(launchctl_user_domain)"
if [[ -f "${PLIST_DEST}" ]] && launchctl print "${domain}/${LABEL}" &>/dev/null; then
  launchctl bootout "${domain}" "${PLIST_DEST}" 2>/dev/null || true
  echo "stopped launchd service: ${LABEL}"
fi

if declare -F kill_port_listeners >/dev/null; then
  pids="$(_lsof -ti tcp:"${PORT}" 2>/dev/null || true)"
  if [[ -n "${pids}" ]]; then
    kill_port_listeners "${PORT}"
    echo "stopped listener on port ${PORT}"
  elif is_port_listening "${PORT}"; then
    echo "port ${PORT} still responds to /health (no lsof PID to stop)"
  else
    echo "no listener on port ${PORT}"
  fi
else
  echo "no listener on port ${PORT}"
fi
