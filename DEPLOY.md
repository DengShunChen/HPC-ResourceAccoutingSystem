# 叢集部署指南 (Cluster Deployment Guide)

本文件旨在說明如何將「運算資源帳務系統」部署到一個多使用者的 Linux 叢集環境中。

## 核心部署概念

- **服務節點 (Service Node)**: 所有常駐服務 (Streamlit, Redis) 都應在登入節點或專用的服務節點上執行，而非計算節點。
- **自動化 (Automation)**: 資料載入應透過 `cron` 排程任務自動定期執行，確保資料的時效性。
- **共享儲存 (Shared Storage)**: 專案檔案、SQLite 資料庫和日誌檔都必須存放在共享檔案系統上 (如 NFS)，以確保所有程序都能存取。
- **絕對路徑 (Absolute Paths)**: 為確保腳本在任何執行環境下都能正確運作，所有設定檔和腳本中的路徑都必須使用絕對路徑。

---

## 階段一：環境準備

1.  **部署程式碼**:
    登入您的叢集，並在您選擇的目錄下，透過 `git` 拉取專案。
    ```bash
    # 範例路徑：/home/your_user/apps/
    git clone <您的專案 Git Repo URL> ResourceAccountingSystem
    cd ResourceAccountingSystem
    ```

2.  **建立 Python 環境並安裝相依套件**（擇一）:

    **uv（建議，與 `uv.lock` 可重現安裝）** — 需先安裝 [uv](https://docs.astral.sh/uv/getting-started/installation/)：
    ```bash
    uv sync
    source .venv/bin/activate   # 或直接用 uv run …，不必 activate
    ```

    **傳統 venv + pip**（環境目錄固定為 `.venv`）:
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    ```

---

## 階段二：設定檔配置（建議「只動環境變數」，避免手改 repo）

**路徑請用絕對路徑。**

### 快速初始化（可選）

在專案根目錄執行（若已安裝 **uv** 則 `uv sync`；否則建立 `.venv` 並以 pip 安裝；若無 `.env` 則從 `.env.example` 複製；並跑 `alembic upgrade head`）：

```bash
bash scripts/deploy_setup.sh
```

### 手動設定

1.  **環境變數 (`.env`)** — 部署時**優先**只維護此檔，不必改 `config.ini` 內的 placeholder：
    ```bash
    cp .env.example .env
    nano .env
    ```
    至少設定（範例，請替換為實際絕對路徑）：
    ```env
    DATABASE_FILE=/path/to/your/ResourceAccountingSystem/resource_accounting.db
    LOG_DIRECTORY_PATH=/path/to/your/cluster_job_logs
    REDIS_HOST=127.0.0.1
    REDIS_PORT=6379
    ```
    選用：
    - `HPC_ACCOUNTING_CONFIG`：自訂 `config.ini` 路徑（預設為專案根目錄的 `config.ini`）。
    - `CLUSTER_ID`：強制指定邏輯叢集 id（覆寫 hostname / `active_cluster`）。
    - 多叢集時，`config.ini` 內各 `[cluster_<id>]` 的 `host_aliases` 可讓服務節點依 **hostname** 自動對應，減少每台手動設 `CLUSTER_ID`。

2.  **`config.ini`**（可選）:
    若已設定 `LOG_DIRECTORY_PATH`，則**不需要**再改 `[data] log_directory_path`。僅在需調整叢集容量、`host_aliases` 或 `column_names` 時編輯 `config.ini`。

3.  **初始化/升級資料庫**:
    ```bash
    source .venv/bin/activate
    alembic upgrade head
    ```

---

## 階段三：啟動核心服務 (背景執行)

我們使用 `nohup` 和 `&` 來確保服務在您登出後依然持續運行。

1.  **啟動 Redis**:
    ```bash
    nohup redis-server &
    ```
    日誌會輸出到 `nohup.out`。

2.  **啟動 Streamlit 網頁服務**:
    `--server.address=0.0.0.0` 是讓其他使用者能連線的關鍵。
    ```bash
    # 您可以將 8501 換成您想要的埠號
    nohup streamlit run 系統登入.py --server.address=0.0.0.0 --server.port=8501 &
    ```

---

## 階段四：設定自動化資料載入 (Cron Job)

1.  執行 `crontab -e` 來編輯您的排程任務。

2.  在檔案末尾加入一行；**路徑改為你的專案根目錄**。`data_loader` 會自動載入專案根目錄的 `.env`（內含 `LOG_DIRECTORY_PATH` 等），無須在 cron 裡重複 `export`。
    ```crontab
    # 每小時第 5 分鐘載入日誌（使用 repo 內腳本，固定 .venv/bin/python）
    5 * * * * /path/to/your/ResourceAccountingSystem/scripts/run_data_loader.sh >> /path/to/your/ResourceAccountingSystem/cron.log 2>&1
    ```

---

## 階段五：驗證與服務管理

1.  **驗證服務狀態**:
    ```bash
    # 檢查 Streamlit 服務
    ps aux | grep streamlit

    # 檢查 Redis 服務
    ps aux | grep redis-server
    ```

2.  **存取應用程式**:
    -   請與您的叢集管理員確認，服務節點的防火牆是否允許外部流量連線到您設定的埠號 (例如 `8501`)。
    -   在您的瀏覽器中，輸入 `http://<您的服務節點IP或主機名稱>:8501`。

3.  **停止服務**:
    使用 `ps` 指令找到服務的程序 ID (PID)，然後使用 `kill` 指令停止它。
    ```bash
    # 範例：假設 Streamlit 的 PID 是 12345
    kill 12345
    ```

## 部署檢查清單

- [ ] 程式碼已部署到叢集上的指定目錄。
- [ ] Python 虛擬環境 `.venv` 已建立（`uv sync` 或 `python3 -m venv .venv` + pip）並可執行 `.venv/bin/python`。
- [ ] 相依套件已安裝（`uv.lock` / `uv sync` 或 `pip install -r requirements.txt`）。
- [ ] `.env` 檔案已在叢集上建立，並包含正確的**絕對路徑**（至少 `DATABASE_FILE`、`LOG_DIRECTORY_PATH`）。
- [ ] 日誌目錄已透過 `LOG_DIRECTORY_PATH`（或 `config.ini`）指向叢集上的**實際路徑**。
- [ ] 資料庫已透過 `alembic upgrade head` 初始化。
- [ ] Redis 服務已在背景啟動。
- [ ] `cron` 排程任務已設定，並指向正確的**絕對路徑**。
- [ ] Streamlit 服務已使用 `nohup` 和 `--server.address=0.0.0.0` 在背景啟動。
- [ ] 防火牆規則已確認。
