#!/usr/bin/env bash
# Linux: run Family Media Center (systemd ExecStart)
set -euo pipefail

_set_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${_set_dir}/lib/paths.sh" ]]; then
  source "${_set_dir}/lib/paths.sh"
else
  source "${_set_dir}/../lib/paths.sh"
fi
mediacenter_init_paths || exit 1
PYTHON="${APP_ROOT}/.venv/bin/python"

if [[ ! -x "${PYTHON}" ]]; then
  echo "ERROR: .venv not found. Run ./service.sh install first." >&2
  exit 1
fi

export PYTHONUNBUFFERED=1
export PYTHONUTF8=1
cd "${APP_ROOT}"
exec "${PYTHON}" -u -m app.main
