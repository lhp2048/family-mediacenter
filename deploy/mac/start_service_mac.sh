#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FORCE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --force) FORCE=1; shift ;;
    *) shift ;;
  esac
done
if [[ "${FORCE}" -eq 1 ]]; then
  exec bash "${SCRIPT_DIR}/restart_service_mac.sh" --force
fi
exec bash "${SCRIPT_DIR}/restart_service_mac.sh"
