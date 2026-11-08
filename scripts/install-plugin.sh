#!/usr/bin/env bash
# 把插件装进 DSH 的 web profile。装完必须重启 `dsh web` 才会加载。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROFILE="${DSH_PROFILE:-web}"

echo "→ profile: $PROFILE"
echo "→ 包目录: $ROOT"

if ! command -v dsh >/dev/null 2>&1; then
  echo "找不到 dsh 命令，先确认 Node/npm 全局装过 @deepseek-ai/dsh" >&2
  exit 1
fi

dsh plugin --profile "$PROFILE" add "$ROOT"

cat <<'EOF'

插件安装完成。重启 dsh web 后浮窗自动出现。
登录时启动可在桌宠菜单中开启。
EOF
