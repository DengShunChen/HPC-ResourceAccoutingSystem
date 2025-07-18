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

2.  **建立並啟用 Python 虛擬環境**:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **安裝相依套件**:
    ```bash
    pip install -r requirements.txt
    ```

---

## 階段二：設定檔配置

**這是部署中最關鍵的一步，請務必使用絕對路徑！**

1.  **設定環境變數 (`.env`)**:
    建立 `.env` 檔案，並填寫以下內容。
    ```bash
    nano .env
    ```
    檔案內容 (請替換為您的實際路徑):
    ```env
    DATABASE_FILE="/path/to/your/ResourceAccountingSystem/resource_accounting.db"
    REDIS_HOST="127.0.0.1"
    REDIS_PORT="6379"
    ```

2.  **設定應用程式組態 (`config.ini`)**:
    編輯 `config.ini`，確保 `log_directory_path` 指向叢集上**實際存放 `.out` 日誌檔的目錄**。
    ```bash
    nano config.ini
    ```
    檔案內容 (請替換為您的實際路徑):
    ```ini
    [data]
    log_directory_path = /path/to/your/cluster_job_logs/
    
    [log_schema]
    # ... (其他設定保持不變)
    ```

3.  **初始化/升級資料庫**:
    執行 Alembic 指令，根據程式碼中的模型建立或更新資料庫檔案及資料表。
    ```bash
    # 在虛擬環境 (venv) 已啟用的狀態下執行
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

2.  在檔案末尾加入以下這一行，**請務必將所有路徑替換成您的絕對路徑**。
    ```crontab
    # 每一小時的第 5 分鐘，執行資源帳務系統的資料載入腳本
    # 將標準輸出和錯誤輸出都附加到 cron.log 檔案中，方便追蹤
    5 * * * * cd /path/to/your/ResourceAccountingSystem && source venv/bin/activate && python data_loader.py >> /path/to/your/ResourceAccountingSystem/cron.log 2>&1
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
- [ ] Python 虛擬環境已建立並啟用。
- [ ] `requirements.txt` 中的套件已安裝。
- [ ] `.env` 檔案已在叢集上建立，並包含正確的**絕對路徑**。
- [ ] `config.ini` 中的日誌路徑已更新為叢集上的**實際路徑**。
- [ ] 資料庫已透過 `alembic upgrade head` 初始化。
- [ ] Redis 服務已在背景啟動。
- [ ] `cron` 排程任務已設定，並指向正確的**絕對路徑**。
- [ ] Streamlit 服務已使用 `nohup` 和 `--server.address=0.0.0.0` 在背景啟動。
- [ ] 防火牆規則已確認。
