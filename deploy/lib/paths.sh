#!/usr/bin/env bash
# Resolve APP_ROOT / LIB_DIR / SCRIPT_DIR for dist (scripts/) vs source (deploy/mac|linux/) layouts.

mediacenter_init_paths() {
  local caller="${BASH_SOURCE[1]:-${BASH_SOURCE[0]}}"
  SCRIPT_DIR="$(cd "$(dirname "${caller}")" && pwd)"
  if [[ -f "${SCRIPT_DIR}/../pyproject.toml" ]]; then
    APP_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
  elif [[ -f "${SCRIPT_DIR}/../../pyproject.toml" ]]; then
    APP_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
  else
    echo "ERROR: pyproject.toml not found near ${SCRIPT_DIR}" >&2
    return 1
  fi
  if [[ -d "${SCRIPT_DIR}/lib" ]]; then
    LIB_DIR="${SCRIPT_DIR}/lib"
  elif [[ -d "${SCRIPT_DIR}/../lib" ]]; then
    LIB_DIR="$(cd "${SCRIPT_DIR}/../lib" && pwd)"
  else
    LIB_DIR=""
  fi
}

mediacenter_source_lib() {
  local base dir
  base="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  for dir in "${base}" "${base}/.."; do
    if [[ -f "${dir}/paths.sh" ]]; then
      # shellcheck source=paths.sh
      source "${dir}/paths.sh"
      return 0
    fi
    if [[ -f "${dir}/lib/paths.sh" ]]; then
      # shellcheck source=lib/paths.sh
      source "${dir}/lib/paths.sh"
      return 0
    fi
  done
  echo "ERROR: paths.sh not found" >&2
  return 1
}
