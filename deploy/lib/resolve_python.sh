#!/usr/bin/env bash
# Resolve Python >= 3.10 for Family Media Center venv.
# Usage:
#   source scripts/lib/resolve_python.sh
#   resolve_python_bin
#   mediacenter_setup_venv /path/to/app

MEDIACENTER_MIN_PYTHON_MAJOR=3
MEDIACENTER_MIN_PYTHON_MINOR=10

MEDIACENTER_PYTHON_CANDIDATES=(
  python3.13
  python3.12
  python3.11
  python3.10
  /opt/homebrew/bin/python3.13
  /opt/homebrew/bin/python3.12
  /opt/homebrew/bin/python3.11
  /opt/homebrew/bin/python3.10
  /usr/local/bin/python3.13
  /usr/local/bin/python3.12
  /usr/local/bin/python3.11
  /usr/local/bin/python3.10
  /Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13
  /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12
  /Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11
  /Library/Frameworks/Python.framework/Versions/3.10/bin/python3.10
)

_python_meets_minimum() {
  local bin="$1"
  "${bin}" -c "import sys; raise SystemExit(0 if sys.version_info >= (${MEDIACENTER_MIN_PYTHON_MAJOR}, ${MEDIACENTER_MIN_PYTHON_MINOR}) else 1)" 2>/dev/null
}

_python_try_select() {
  local bin="$1"
  if [[ -x "${bin}" ]]; then
    :
  elif command -v "${bin}" >/dev/null 2>&1; then
    bin="$(command -v "${bin}")"
  else
    return 1
  fi
  if _python_meets_minimum "${bin}"; then
    RESOLVED_PYTHON="${bin}"
    RESOLVED_PYTHON_VERSION="$("${bin}" --version 2>&1 | head -n 1)"
    return 0
  fi
  return 1
}

_list_python_candidates() {
  local c seen=""
  for c in python3.13 python3.12 python3.11 python3.10 python3 python3.9 \
    /opt/homebrew/bin/python3.12 /usr/local/bin/python3.12; do
    if [[ -x "${c}" ]] || command -v "${c}" >/dev/null 2>&1; then
      local bin="${c}"
      [[ -x "${bin}" ]] || bin="$(command -v "${bin}")"
      case " ${seen} " in
        *" ${bin} "*) continue ;;
      esac
      seen="${seen} ${bin}"
      echo "  ${bin}: $("${bin}" --version 2>&1 | head -n 1)"
    fi
  done
}

resolve_python_bin() {
  local requested="${1:-}"
  RESOLVED_PYTHON=""
  RESOLVED_PYTHON_VERSION=""

  if [[ -n "${requested}" ]]; then
    _python_try_select "${requested}" && return 0
    echo "ERROR: ${requested} not found or Python < ${MEDIACENTER_MIN_PYTHON_MAJOR}.${MEDIACENTER_MIN_PYTHON_MINOR}" >&2
    return 1
  fi

  if [[ -n "${PYTHON_BIN:-}" ]]; then
    _python_try_select "${PYTHON_BIN}" && return 0
    echo "ERROR: PYTHON_BIN=${PYTHON_BIN} is not usable (need >= 3.10)" >&2
    return 1
  fi

  local c
  for c in "${MEDIACENTER_PYTHON_CANDIDATES[@]}"; do
    _python_try_select "${c}" && return 0
  done

  if command -v python3 >/dev/null 2>&1; then
    _python_try_select "$(command -v python3)" && return 0
  fi

  echo "ERROR: Python >= ${MEDIACENTER_MIN_PYTHON_MAJOR}.${MEDIACENTER_MIN_PYTHON_MINOR} required." >&2
  echo "Install python3.12 or run: PYTHON_BIN=python3.12 ./service.sh install" >&2
  echo "Detected:" >&2
  _list_python_candidates >&2
  return 1
}

_venv_needs_recreate() {
  local app_root="$1"
  local venv_py="${app_root}/.venv/bin/python"
  [[ ! -x "${venv_py}" ]] && return 0
  if ! "${venv_py}" -c "import sys; sys.exit(0 if sys.version_info >= (${MEDIACENTER_MIN_PYTHON_MAJOR}, ${MEDIACENTER_MIN_PYTHON_MINOR}) else 1)" 2>/dev/null; then
    return 0
  fi
  return 1
}

mediacenter_setup_venv() {
  local app_root="$1"
  local requested="${2:-}"
  local venv="${app_root}/.venv"
  local venv_py="${venv}/bin/python"

  if ! resolve_python_bin "${requested}"; then
    return 1
  fi

  if _venv_needs_recreate "${app_root}"; then
    if [[ -d "${venv}" ]]; then
      echo "==> Removing old .venv (need Python >= ${MEDIACENTER_MIN_PYTHON_MAJOR}.${MEDIACENTER_MIN_PYTHON_MINOR})"
      rm -rf "${venv}"
    fi
  fi

  if [[ ! -x "${venv_py}" ]]; then
    echo "==> Creating venv"
    echo "    ${RESOLVED_PYTHON}"
    echo "    ${RESOLVED_PYTHON_VERSION}"
    "${RESOLVED_PYTHON}" -m venv "${venv}"
  else
    echo "==> Using existing venv"
    echo "    ${venv_py}"
    echo "    $("${venv_py}" --version 2>&1 | head -n 1)"
  fi

  echo "==> Installing dependencies"
  "${venv_py}" -m pip install -U pip setuptools wheel -q
  "${venv_py}" -m pip install -e "${app_root}" -q
  "${venv_py}" -m pip install yt-dlp -q

  echo "==> Verify imports"
  (cd "${app_root}" && "${venv_py}" -c "import uvicorn; from app.main import app") || {
    echo "ERROR: dependency install failed" >&2
    return 1
  }

  MEDIACENTER_PYTHON="${venv_py}"
  export MEDIACENTER_PYTHON
  return 0
}

show_mediacenter_python_info() {
  local app_root="$1"
  local venv_py="${app_root}/.venv/bin/python"
  echo "Python candidates:"
  _list_python_candidates
  if [[ -x "${venv_py}" ]]; then
    echo "Active venv: ${venv_py}"
    echo "  $("${venv_py}" --version 2>&1 | head -n 1)"
  else
    echo "Active venv: (none)"
  fi
}

patch_config_server() {
  local app_root="$1"
  local host="$2"
  local port="$3"
  local py="${4:-${app_root}/.venv/bin/python}"
  [[ -x "${py}" ]] || return 1
  MEDIACENTER_APP_ROOT="${app_root}" MEDIACENTER_HOST="${host}" MEDIACENTER_PORT="${port}" "${py}" - <<'PY'
import os
from pathlib import Path
import yaml

root = Path(os.environ["MEDIACENTER_APP_ROOT"])
cfg_path = root / "config.yaml"
data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) if cfg_path.is_file() else {}
if not isinstance(data, dict):
    data = {}
server = data.setdefault("server", {})
server["host"] = os.environ["MEDIACENTER_HOST"]
server["port"] = int(os.environ["MEDIACENTER_PORT"])
cfg_path.write_text(yaml.safe_dump(data, allow_unicode=True, default_flow_style=False), encoding="utf-8")
print(f"  config.yaml server.host={server['host']} port={server['port']}")
PY
}

ensure_runtime_dirs() {
  local app_root="$1"
  mkdir -p "${app_root}/logs" "${app_root}/data" "${app_root}/downloads/multimedia"
}

wait_for_health() {
  local port="$1"
  local i
  for i in $(seq 1 25); do
    if curl -sf --max-time 2 "http://127.0.0.1:${port}/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}
