#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="family-mediacenter"
_set_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${_set_dir}/lib/paths.sh" ]]; then
  source "${_set_dir}/lib/paths.sh"
else
  source "${_set_dir}/../lib/paths.sh"
fi
mediacenter_init_paths || exit 1
RUN_SCRIPT="${SCRIPT_DIR}/run_service.sh"
LOG_DIR="${APP_ROOT}/logs"

if [[ -f "${LIB_DIR}/resolve_python.sh" ]]; then
  # shellcheck source=lib/resolve_python.sh
  source "${LIB_DIR}/resolve_python.sh"
fi

PORT="18026"
DO_FORCE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --force) DO_FORCE=1; shift ;;
    --port)  PORT="${2:-18026}"; shift 2 ;;
    *) shift ;;
  esac
done

bash "${SCRIPT_DIR}/stop_service_linux.sh"
systemctl --user restart "${SERVICE_NAME}.service" 2>/dev/null || true
sleep 2

if ! wait_for_health "${PORT}"; then
  echo "systemd restart failed, trying background start"
  mkdir -p "${LOG_DIR}"
  chmod +x "${RUN_SCRIPT}" 2>/dev/null || true
  nohup bash "${RUN_SCRIPT}" >> "${LOG_DIR}/service.out.log" 2>> "${LOG_DIR}/service.err.log" &
  disown $! 2>/dev/null || true
  sleep 2
fi

if wait_for_health "${PORT}"; then
  echo "OK: http://127.0.0.1:${PORT}/"
else
  echo "ERROR: restart failed" >&2
  exit 1
fi
