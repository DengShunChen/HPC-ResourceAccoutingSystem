#!/usr/bin/env bash
# Cron / systemd 用：在 repo 根目錄執行 data_loader（讀 .env；日誌路徑可用 LOG_DIRECTORY_PATH）
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="${ROOT}/venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "找不到 $PY，請先 python3 -m venv venv && pip install -r requirements.txt" >&2
  exit 1
fi
exec "$PY" "$ROOT/data_loader.py" "$@"
