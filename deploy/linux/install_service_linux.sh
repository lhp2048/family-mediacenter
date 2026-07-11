#!/usr/bin/env bash
# Linux: setup venv + systemd user service
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
UNIT_DIR="${HOME}/.config/systemd/user"
UNIT_FILE="${UNIT_DIR}/${SERVICE_NAME}.service"

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

while [[ $# -gt 0 ]]; do
  case "$1" in
    --uninstall) DO_UNINSTALL=1; shift ;;
    --status)    DO_STATUS=1; shift ;;
    --port)      PORT="${2:-18026}"; shift 2 ;;
    --bind)      BIND="${2:-0.0.0.0}"; shift 2 ;;
    -h|--help)   usage; exit 0 ;;
    *) echo "unknown arg: $1" >&2; usage; exit 1 ;;
  esac
done

if [[ "$(uname -s)" == "Darwin" ]]; then
  echo "error: use scripts/install_service_mac.sh on macOS" >&2
  exit 1
fi

if [[ "${DO_STATUS}" -eq 1 ]]; then
  echo "App root: ${APP_ROOT}"
  echo "Unit: ${UNIT_FILE}"
  systemctl --user status "${SERVICE_NAME}.service" --no-pager 2>/dev/null || echo "not installed"
  [[ -x "${APP_ROOT}/.venv/bin/python" ]] && "${APP_ROOT}/.venv/bin/python" --version || echo "venv not ready"
  exit 0
fi

if [[ "${DO_UNINSTALL}" -eq 1 ]]; then
  systemctl --user disable --now "${SERVICE_NAME}.service" 2>/dev/null || true
  rm -f "${UNIT_FILE}"
  systemctl --user daemon-reload
  if declare -F kill_port_listeners >/dev/null; then
    kill_port_listeners "${PORT}"
  fi
  echo "uninstalled ${SERVICE_NAME}"
  exit 0
fi

if [[ ! -f "${APP_ROOT}/pyproject.toml" ]]; then
  echo "error: run from install dir with pyproject.toml" >&2
  exit 1
fi

chmod +x "${RUN_SCRIPT}" "${SCRIPT_DIR}/start_service_linux.sh" "${SCRIPT_DIR}/restart_service_linux.sh" "${SCRIPT_DIR}/stop_service_linux.sh" 2>/dev/null || true

mediacenter_setup_venv "${APP_ROOT}" || exit 1
PYTHON="${APP_ROOT}/.venv/bin/python"
patch_config_server "${APP_ROOT}" "${BIND}" "${PORT}" "${PYTHON}" || exit 1
ensure_runtime_dirs "${APP_ROOT}"

if declare -F kill_port_listeners >/dev/null; then
  kill_port_listeners "${PORT}"
fi

mkdir -p "${UNIT_DIR}"

cat > "${UNIT_FILE}" <<EOF
[Unit]
Description=Family Media Center
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${APP_ROOT}
ExecStart=/bin/bash ${RUN_SCRIPT}
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now "${SERVICE_NAME}.service"
sleep 2

if wait_for_health "${PORT}"; then
  echo "OK: http://127.0.0.1:${PORT}/"
else
  echo "warn: /health not ready, check: journalctl --user -u ${SERVICE_NAME} -n 50"
fi

echo "enable linger for boot without login: loginctl enable-linger \$USER"
if declare -F print_access_urls >/dev/null; then
  print_access_urls "${PORT}" "${BIND}"
fi
