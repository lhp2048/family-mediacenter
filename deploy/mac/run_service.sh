#!/usr/bin/env bash
# Family Media Center — launchd / foreground start (deploy listens 0.0.0.0 via config.yaml)
set -euo pipefail

_set_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${_set_dir}/lib/paths.sh" ]]; then
  source "${_set_dir}/lib/paths.sh"
else
  source "${_set_dir}/../lib/paths.sh"
fi
mediacenter_init_paths || exit 1

if [[ ! -f "${APP_ROOT}/pyproject.toml" ]]; then
  echo "错误: 未找到 ${APP_ROOT}/pyproject.toml" >&2
  exit 1
fi

PYTHON="${APP_ROOT}/.venv/bin/python"
if [[ ! -x "${PYTHON}" ]]; then
  echo "错误: 未找到 .venv，请先 ./service.sh install" >&2
  exit 1
fi

export PYTHONUNBUFFERED=1
export PYTHONUTF8=1
cd "${APP_ROOT}"
exec "${PYTHON}" -u -m app.main
