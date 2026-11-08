#!/usr/bin/env bash
# 跑浮窗。参数原样透传给 app/main.py。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -x .venv/bin/python ]]; then
  "$ROOT/scripts/setup.sh"
fi

exec ./.venv/bin/python app/main.py "$@"
