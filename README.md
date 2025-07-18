# 運算資源帳務系統

## 專案簡介

這是一個用於管理運算資源帳務的系統，提供 GUI (基於 Streamlit) 和 CLI (基於 Typer) 兩種介面。系統能夠自動掃描指定目錄下的日誌檔，處理新增的資料，並提供高效的查詢、報表生成以及帳戶管理功能。

## 技術棧

*   **應用程式框架 (GUI)**: Streamlit
*   **應用程式框架 (CLI)**: Typer
*   **資料庫**: SQLite (檔案型資料庫)
*   **資料庫版本控制**: Alembic (待實作)
*   **快取**: Redis
*   **測試框架**: Pytest
*   **核心邏輯**: Python (Pandas, SQLAlchemy)

## 資料庫綱要

*   `jobs`: 儲存處理過的日誌資料。
*   `users`: 儲存使用者帳戶資訊。
*   `quotas`: 儲存帳戶的資源使用額度。
*   `group_mappings`: 儲存群組至帳戶的對應例外規則。
*   `processed_files`: 記錄已載入的檔案及其校驗和。
*   `alembic_version`: (由 Alembic 自動管理) 追蹤資料庫版本。

## 開發與部署指南

### 1. 環境設定與初始化

1.  **安裝環境需求**:
    *   確保系統已安裝 Python 3.8+。
    *   **SQLite**: 無需額外伺服器安裝，資料庫將是一個檔案。
    *   **Redis**: 確保 Redis 服務正在運行。如果尚未安裝，請參考 [Redis 官方文件](https://redis.io/docs/getting-started/installation/) 或使用 Homebrew (macOS): `brew install redis`。

2.  **建立並啟用 Python 虛擬環境**:

    ```bash
    python3 -m venv venv
    source venv/bin/activate  # macOS/Linux
    # venv\Scripts\activate   # Windows
    ```

3.  **設定 `.env` 檔案**:
    複製 `.env.example` 為 `.env`，並根據您的環境修改。

    ```bash
    cp .env.example .env
    # 編輯 .env 檔案，例如設定 DATABASE_FILE, REDIS_HOST, REDIS_PORT
    ```

4.  **安裝相依套件**:

    ```bash
    pip install -r requirements.txt
    ```

5.  **初始化資料庫**:
    這將會建立 `resource_accounting.db` 檔案及所有必要的資料表。

    ```bash
    python database.py
    ```

6.  **建立初始管理員帳號 (CLI)**:
    首次運行時，您可以透過 CLI 建立一個管理員帳號。

    ```bash
    python auth.py
    ```
    按照提示輸入管理員使用者名稱和密碼。

### 2. 運行應用程式

#### 2.1. 運行 Streamlit GUI

```bash
streamlit run app.py
```

#### 2.2. 運行 Typer CLI

```bash
python cli.py --help
# 更多 CLI 指令請參考 --help 輸出
```

### 3. 資料載入

將您的日誌檔 (例如 `.out` 檔案) 放置在 `config.ini` 中 `[data]` 部分 `log_directory_path` 所指定的目錄。然後運行資料載入器：

```bash
python data_loader.py
```

### 4. 運行測試

```bash
PYTHONPATH=. pytest
```

## 專案結構

```
.env                  # 環境變數 (不提交到版本控制)
.env.example          # 環境變數範例
app.py                # Streamlit GUI 主程式
auth.py               # 使用者認證與授權邏輯
cli.py                # Typer CLI 主程式 (待實作)
config.ini            # 應用程式配置
data_loader.py        # 日誌資料載入與轉換邏輯
database.py           # 資料庫模型與連線設定
GEMINI.md             # 專案開發藍圖與筆記
queries.py            # 資料庫查詢功能
requirements.txt      # Python 相依套件列表
resource_accounting.db # SQLite 資料庫檔案 (自動生成)
__pycache__/          # Python 編譯快取
data/                 # 存放原始日誌檔的目錄
pages/                # Streamlit 頁面檔案
├── 1_📊_User_Dashboard.py
└── 2_⚙️_Admin_Panel.py
setup_scripts/        # 設定腳本
├── setup_macos.sh    # macOS 設定腳本 (待實作)
tests/                # 單元測試
├── test_auth.py
├── test_database.py
├── test_data_loader.py
└── test_queries.py
venv/                 # Python 虛擬環境
```

## 擴展性考量

*   **資料庫**: 目前使用 SQLite，適合中小型應用。若需處理大量併發寫入或極大資料集，可考慮遷移至 PostgreSQL 或 MySQL。
*   **快取**: Redis 已整合，可有效降低資料庫讀取壓力。
*   **水平擴展**: Streamlit 和 Typer 應用可獨立部署，並可透過負載平衡器進行水平擴展。
*   **Alembic**: 已規劃使用 Alembic 進行資料庫版本控制，確保資料庫結構變更的可追溯性與部署的平滑性。

## 貢獻

歡迎任何形式的貢獻！請遵循以下步驟：

1.  Fork 本專案。
2.  建立您的功能分支 (`git checkout -b feature/AmazingFeature`).
3.  提交您的變更 (`git commit -m 'Add some AmazingFeature'`).
4.  推送到分支 (`git push origin feature/AmazingFeature`).
5.  開啟一個 Pull Request。
