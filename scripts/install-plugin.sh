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

装完了。接下来：
  1. 重启 DSH：  dsh web
  2. 确认插件活着：curl -s http://127.0.0.1:8791/health
      期望：{"ok":true,"plugin":"dsh-whale-girl",...}
  3. 跑浮窗：    ./scripts/run.sh --check   （先自检）
                 ./scripts/run.sh           （正式跑）

端口/模型想改：改 ~/.dsh/profiles/<profile>/cordis.patch.yml 里 whale-girl 的 config，
或者改本仓库 cordis.patch.yml 后重装。改完都要重启 dsh web。
EOF
