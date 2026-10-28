#!/usr/bin/env bash
# 本地开发：自动 venv、释放端口、热重载（默认 :18026）
# 用法: ./scripts/dev.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
HOST="${MEDIACENTER_DEV_HOST:-127.0.0.1}"
PORT="${MEDIACENTER_DEV_PORT:-18026}"

if [[ ! -x "${ROOT}/.venv/bin/python" ]]; then
  echo "[.venv 不存在] 正在初始化..."
  "${SCRIPT_DIR}/setup_venv.sh"
fi

# shellcheck source=/dev/null
source "${ROOT}/.venv/bin/activate"
pip install -e "${ROOT}" -q
pip install yt-dlp -q

pids="$(lsof -ti "tcp:${PORT}" 2>/dev/null || true)"
if [[ -n "${pids}" ]]; then
  echo "停止占用端口 ${PORT} 的进程: ${pids}"
  kill ${pids} 2>/dev/null || true
fi

export MEDIACENTER_DEV_HOST="${HOST}"
export MEDIACENTER_DEV_PORT="${PORT}"
export PYTHONUNBUFFERED=1

echo "========================================"
echo "Family Media Center [DEV]"
echo "服务根目录: ${ROOT}"
echo "地址: http://${HOST}:${PORT}/"
echo "修改 app/ 后自动重载"
echo "按 Ctrl+C 停止"
echo "========================================"

exec python "${ROOT}/scripts/run_dev.py"
