#!/usr/bin/env bash
# 初次部署：venv、依賴、.env 範本、alembic；路徑僅需在 .env 或環境變數設定，不必改 config.ini
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -d venv ]]; then
  python3 -m venv venv
fi
./venv/bin/pip install -U pip
./venv/bin/pip install -r requirements.txt

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "已建立 .env（由 .env.example）；請至少設定 DATABASE_FILE、LOG_DIRECTORY_PATH（絕對路徑）"
else
  echo "已存在 .env，略過複製"
fi

./venv/bin/alembic upgrade head
echo "完成。啟動範例："
echo "  export LOG_DIRECTORY_PATH=/絕對路徑/到/job_logs"
echo "  ./venv/bin/streamlit run 系統登入.py --server.address=0.0.0.0 --server.port=8501"
