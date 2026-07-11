#!/usr/bin/env bash
# Install entry (REQ): delegates to service.sh install
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${ROOT}/service.sh" install "$@"
