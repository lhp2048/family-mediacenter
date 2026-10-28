#!/usr/bin/env bash
# Pack dist into zip + validate manifest + write package-index
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DIST="${ROOT}/dist"
OUT_DIR="${ROOT}/dist_out"

if [[ ! -f "${DIST}/app/main.py" ]]; then
  echo "错误: 请先执行 ./scripts/build.sh" >&2
  exit 1
fi

PYTHON="python3"
if [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PYTHON="${ROOT}/.venv/bin/python"
fi

"${PYTHON}" "${SCRIPT_DIR}/sync_skill_manifest.py" \
  --manifest "${ROOT}/family-product.json" \
  --dist "${DIST}"

"${PYTHON}" "${SCRIPT_DIR}/bump_manifest_version.py" \
  --manifest "${ROOT}/family-product.json" \
  --dist "${DIST}"

"${PYTHON}" "${SCRIPT_DIR}/validate_manifest.py" "${ROOT}/family-product.json" --dist "${DIST}"

ZIP_NAME="$("${PYTHON}" "${SCRIPT_DIR}/read_manifest_field.py" "${ROOT}/family-product.json" zipNameHint family_mediacenter.zip)"
ZIP_FILE="${OUT_DIR}/${ZIP_NAME}"
mkdir -p "${OUT_DIR}"
rm -f "${ZIP_FILE}"

"${PYTHON}" "${SCRIPT_DIR}/make_zip.py" "${DIST}" "${ZIP_FILE}"

"${PYTHON}" "${SCRIPT_DIR}/write_package_info.py" \
  --manifest "${ROOT}/family-product.json" \
  --zip "${ZIP_FILE}" \
  --dist "${DIST}"

echo ""
echo "Packed: ${ZIP_FILE}"
