#!/usr/bin/env bash
# Build dist + pack zip
# Usage: ./scripts/build_and_pack.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"${SCRIPT_DIR}/build.sh"
"${SCRIPT_DIR}/pack.sh"

echo ""
echo "Packed zip supports Windows / Linux / macOS deploy."
echo "See dist/INSTALL.txt after unzip."
