#!/usr/bin/env bash
# Family Media Center 虚拟环境初始化（macOS / Linux）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

LIB="${PROJECT_ROOT}/deploy/lib/resolve_python.sh"
if [[ ! -f "${LIB}" ]]; then
  echo "ERROR: ${LIB} not found" >&2
  exit 1
fi
# shellcheck source=../deploy/lib/resolve_python.sh
source "${LIB}"

if _venv_needs_recreate "${PROJECT_ROOT}"; then
  if [[ -d "${PROJECT_ROOT}/.venv" ]]; then
    echo "==> 删除旧 .venv（Python 版本过低）"
    rm -rf "${PROJECT_ROOT}/.venv"
  fi
fi

mediacenter_setup_venv "${PROJECT_ROOT}" || exit 1

echo ""
echo "完成。开发: ./scripts/dev.sh  服务: ./service.sh install"
