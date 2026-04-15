#!/usr/bin/env bash
# Cron / systemd：使用專案根目錄 .venv 執行 data_loader
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f "${HOME}/.proxy" ]]; then
  # shellcheck disable=SC1091
  source "${HOME}/.proxy"
fi

PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "找不到 ${PY}。請先 bash scripts/deploy_setup.sh" >&2
  exit 1
fi
exec "$PY" "$ROOT/data_loader.py" "$@"
