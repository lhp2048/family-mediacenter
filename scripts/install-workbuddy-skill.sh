#!/usr/bin/env bash
# 安装 Family Media Center WorkBuddy Skill
# 用法:
#   ./scripts/install-workbuddy-skill.sh                    # 从本仓库复制
#   ./scripts/install-workbuddy-skill.sh http://host:18026 # 从在线服务下载
#   curl -fsSL http://host:18026/scripts/install-workbuddy-skill.sh | bash -s -- http://host:18026

set -euo pipefail

SKILL_NAME="family-mediacenter"
DEST="$HOME/.workbuddy/skills/$SKILL_NAME"
BASE_URL="${1:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOCAL_SRC="$PROJECT_ROOT/skills/$SKILL_NAME"

log() { echo "[install-workbuddy-skill] $*"; }

install_from_local() {
    if [[ ! -f "$LOCAL_SRC/SKILL.md" ]]; then
        log "错误: 找不到 $LOCAL_SRC/SKILL.md"
        exit 1
    fi
    mkdir -p "$DEST/references"
    cp "$LOCAL_SRC/SKILL.md" "$DEST/SKILL.md"
    if [[ -f "$LOCAL_SRC/references/api.md" ]]; then
        cp "$LOCAL_SRC/references/api.md" "$DEST/references/api.md"
    fi
    log "已从本地仓库安装"
}

install_from_url() {
    local base="${BASE_URL%/}"
    mkdir -p "$DEST/references"
    curl -fsSL "$base/skills/family-mediacenter/SKILL.md" -o "$DEST/SKILL.md"
    curl -fsSL "$base/skills/family-mediacenter/references/api.md" -o "$DEST/references/api.md"
    log "已从 $base 下载安装"
}

if [[ -n "$BASE_URL" ]]; then
    if [[ -f "$LOCAL_SRC/SKILL.md" ]]; then
        install_from_local
    else
        install_from_url
    fi
else
    install_from_local
fi

log "Skill 已安装到: $DEST"
log "请完全退出并重启 WorkBuddy，然后在对话中使用「下载」等关键词触发。"
