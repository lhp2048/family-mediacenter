#!/usr/bin/env bash
# Assemble family_mediacenter dist for zip deploy
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DIST="${ROOT}/dist"

PYTHON="python3"
if [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PYTHON="${ROOT}/.venv/bin/python"
fi

echo "==> 组装 dist"
rm -rf "${DIST}"
mkdir -p "${DIST}/scripts/lib" "${DIST}/data" "${DIST}/downloads/multimedia" "${DIST}/logs"

cp -R "${ROOT}/app" "${DIST}/app"
find "${DIST}/app" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
cp -R "${ROOT}/skills" "${DIST}/skills"
if [[ -d "${ROOT}/mcp_server" ]]; then
  cp -R "${ROOT}/mcp_server" "${DIST}/mcp_server"
  find "${DIST}/mcp_server" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
fi

cp "${ROOT}/config.yaml" "${DIST}/config.yaml"
cp "${ROOT}/pyproject.toml" "${DIST}/pyproject.toml"
[[ -f "${ROOT}/docker-compose.yml" ]] && cp "${ROOT}/docker-compose.yml" "${DIST}/docker-compose.yml"
cp "${ROOT}/family-product.json" "${DIST}/family-product.json"
cp "${ROOT}/deploy/INSTALL.txt" "${DIST}/INSTALL.txt"

for name in service install; do
  [[ -f "${ROOT}/deploy/${name}.bat" ]] && cp "${ROOT}/deploy/${name}.bat" "${DIST}/${name}.bat"
  [[ -f "${ROOT}/deploy/${name}.sh" ]] && cp "${ROOT}/deploy/${name}.sh" "${DIST}/${name}.sh"
done

cp "${ROOT}/deploy/windows/"*.bat "${DIST}/scripts/" 2>/dev/null || true
cp "${ROOT}/deploy/linux/"*.sh "${DIST}/scripts/"
cp "${ROOT}/deploy/mac/"*.sh "${DIST}/scripts/"
cp "${ROOT}/deploy/lib/"*.sh "${DIST}/scripts/lib/" 2>/dev/null || true

for name in install-workbuddy-skill install-skill; do
  [[ -f "${ROOT}/scripts/${name}.sh" ]] && cp "${ROOT}/scripts/${name}.sh" "${DIST}/scripts/${name}.sh"
  [[ -f "${ROOT}/scripts/${name}.bat" ]] && cp "${ROOT}/scripts/${name}.bat" "${DIST}/scripts/${name}.bat"
  [[ -f "${ROOT}/scripts/${name}.ps1" ]] && cp "${ROOT}/scripts/${name}.ps1" "${DIST}/scripts/${name}.ps1"
done

chmod +x "${DIST}/scripts/"*.sh "${DIST}/"*.sh 2>/dev/null || true
chmod +x "${DIST}/scripts/lib/"*.sh 2>/dev/null || true

"${PYTHON}" "${SCRIPT_DIR}/normalize_shell.py" "${ROOT}/deploy" "${DIST}"

"${PYTHON}" "${SCRIPT_DIR}/validate_manifest.py" "${ROOT}/family-product.json" --dist "${DIST}"

echo ""
echo "构建完成: ${DIST}"
echo "打 zip: ${ROOT}/scripts/pack.sh"
