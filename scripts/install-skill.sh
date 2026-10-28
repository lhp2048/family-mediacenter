#!/usr/bin/env bash
# 安装 Family Media Center Cursor Skill（通用 skill 安装脚本）
# WorkBuddy 请使用: ./scripts/install-workbuddy-skill.sh
#
# 用法:
#   ./scripts/install-skill.sh              # 安装到 monorepo 项目 .cursor/skills/
#   ./scripts/install-skill.sh --user       # 安装到 ~/.cursor/skills/
#   ./scripts/install-skill.sh --link       # 符号链接（开发时源改动即时生效）
#   ./scripts/install-skill.sh --host 192.168.2.11
#
set -euo pipefail

SKILL_NAME="family-mediacenter"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WORKSPACE_ROOT="$(cd "${PROJECT_ROOT}/.." && pwd)"
SOURCE_SKILL_DIR="${PROJECT_ROOT}/skills/${SKILL_NAME}"

SCOPE="project"
USE_LINK=0
MEDIACENTER_HOST=""
MEDIACENTER_PORT="18026"

usage() {
  sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --user)   SCOPE="user"; shift ;;
    --project) SCOPE="project"; shift ;;
    --link)   USE_LINK=1; shift ;;
    --host)   MEDIACENTER_HOST="${2:-}"; shift 2 ;;
    --port)   MEDIACENTER_PORT="${2:-18026}"; shift 2 ;;
    -h|--help) usage 0 ;;
    *) echo "未知参数: $1" >&2; usage 1 ;;
  esac
done

if [[ ! -f "${SOURCE_SKILL_DIR}/SKILL.md" ]]; then
  echo "错误: 找不到 ${SOURCE_SKILL_DIR}/SKILL.md" >&2
  exit 1
fi

if [[ "${SCOPE}" == "user" ]]; then
  TARGET_DIR="${HOME}/.cursor/skills/${SKILL_NAME}"
else
  TARGET_DIR="${WORKSPACE_ROOT}/.cursor/skills/${SKILL_NAME}"
fi

mkdir -p "$(dirname "${TARGET_DIR}")"

if [[ -e "${TARGET_DIR}" ]]; then
  rm -rf "${TARGET_DIR}"
fi

if [[ "${USE_LINK}" -eq 1 ]]; then
  ln -s "${SOURCE_SKILL_DIR}" "${TARGET_DIR}"
  echo "已创建符号链接: ${TARGET_DIR} -> ${SOURCE_SKILL_DIR}"
else
  mkdir -p "${TARGET_DIR}/references"
  cp "${SOURCE_SKILL_DIR}/SKILL.md" "${TARGET_DIR}/SKILL.md"
  if [[ -f "${SOURCE_SKILL_DIR}/references/api.md" ]]; then
    cp "${SOURCE_SKILL_DIR}/references/api.md" "${TARGET_DIR}/references/api.md"
  fi
  echo "已复制 Skill 到: ${TARGET_DIR}"
fi

if [[ -n "${MEDIACENTER_HOST}" ]]; then
  BASE="http://${MEDIACENTER_HOST}:${MEDIACENTER_PORT}"
  if [[ -f "${TARGET_DIR}/SKILL.md" ]]; then
    sed -i.bak "s|http://127.0.0.1:18026|${BASE}|g" "${TARGET_DIR}/SKILL.md" 2>/dev/null || \
      sed -i '' "s|http://127.0.0.1:18026|${BASE}|g" "${TARGET_DIR}/SKILL.md"
    rm -f "${TARGET_DIR}/SKILL.md.bak"
    echo "已写入服务地址: ${BASE}"
  fi
fi

echo ""
echo "Cursor Skill 安装完成。"
echo "  目标: ${TARGET_DIR}"
echo "  重启 Cursor 或在 Agent 中 @${SKILL_NAME} 使用。"
