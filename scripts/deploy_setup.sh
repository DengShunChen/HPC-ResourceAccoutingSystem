#!/usr/bin/env bash
# 初次部署：依賴（優先 uv + uv.lock，否則 .venv + pip）、.env 範本、alembic
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# 在 uv / pip 連線 PyPI 之前載入本機 proxy（自管 ~/.proxy，例如 export https_proxy=…）
if [[ -f "${HOME}/.proxy" ]]; then
  # shellcheck disable=SC1091
  source "${HOME}/.proxy"
fi

if command -v uv >/dev/null 2>&1; then
  uv sync
else
  if [[ ! -d .venv ]]; then
    python3 -m venv .venv
  fi
  ./.venv/bin/pip install -U pip
  ./.venv/bin/pip install -r requirements.txt
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "已建立 .env（由 .env.example）；請至少設定 DATABASE_FILE、LOG_DIRECTORY_PATH（絕對路徑）"
else
  echo "已存在 .env，略過複製"
fi

PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "找不到 ${PY}。請安裝 uv（https://docs.astral.sh/uv/）後執行 uv sync，或手動: python3 -m venv .venv" >&2
  exit 1
fi

"$PY" -m alembic upgrade head
echo "完成。"
echo "  uv: uv run streamlit run 系統登入.py --server.address=0.0.0.0 --server.port=8501"
echo "  或:  export LOG_DIRECTORY_PATH=/絕對路徑/到/job_logs"
echo "       ${PY} -m streamlit run 系統登入.py --server.address=0.0.0.0 --server.port=8501"
