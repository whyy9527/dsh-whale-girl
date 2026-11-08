#!/usr/bin/env bash
# 跑浮窗。参数原样透传给 app/main.py。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -x .venv/bin/python ]]; then
  echo "还没建 .venv，先跑 ./scripts/setup.sh" >&2
  exit 1
fi

exec ./.venv/bin/python app/main.py "$@"
