#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="family-mediacenter"
PORT="${PORT:-18026}"

systemctl --user stop "${SERVICE_NAME}.service" 2>/dev/null || true

pids="$(lsof -ti tcp:"${PORT}" 2>/dev/null || true)"
if [[ -n "${pids}" ]]; then
  kill ${pids} 2>/dev/null || true
  sleep 1
  pids="$(lsof -ti tcp:"${PORT}" 2>/dev/null || true)"
  [[ -n "${pids}" ]] && kill -9 ${pids} 2>/dev/null || true
  echo "stopped listener on port ${PORT}"
else
  echo "no listener on port ${PORT}"
fi
