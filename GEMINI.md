# 運算資源帳務系統 - 開發計畫 (V11 - 最終藍圖，SQLite 資料庫)

## 1. 系統目標與架構

### 1.1. 核心目標
- **雙介面**: 提供 GUI 和 CLI。
- **動態資料處理**: 自動掃描指定目錄，僅處理新增的日誌檔。
- **高效查詢**: 提供反應快速的互動式儀表板與即時指令。
- **管理功能**: 提供帳戶、額度、報表及帳務對應規則管理。
- **易於部署與擴展**: 系統易於部署，並可透過負載平衡進行水平擴展。
- **穩健與可維護**: 透過冪等的資料載入、單元測試、資料庫版本控制與安全的設定管理，確保系統的穩定性與長期可維護性。
- **資源計費單位**: CPU 使用 `node hours`，GPU 使用 `core hours`。
- **錢包概念**: 引入錢包概念取代傳統群組，不同群組或使用者可關聯至不同錢包。
- **總覽指標**: 在總覽頁面，CPU 使用 `total_node_hours`，GPU 使用 `total_core_hours`。

### 1.2. 技術架構
- **應用程式框架 (GUI)**: **Streamlit**
- **應用程式框架 (CLI)**: **Typer**
- **資料庫**: **SQLite** (檔案型資料庫)
  - **效能考量**: SQLite 適合中小型應用和單一寫入者。對於大量併發寫入或極大資料集，可能會遇到效能瓶頸。Redis 快取將有助於緩解讀取壓力。
- **資料庫版本控制**: **Alembic**
- **快取**: Redis
- **測試框架**: **Pytest**
- **核心邏輯**: Python (Pandas, SQLAlchemy)，由 GUI 和 CLI 共用。

---

## 2. 資料庫綱要 (Data Schema)
- `jobs`: 儲存處理過的日誌資料。
- `users`: 儲存使用者帳戶資訊。
- `quotas`: 儲存帳戶的資源使用額度。
- `group_mappings`: 儲存群組至帳戶的對應例外規則。
- `processed_files`: 記錄已載入的檔案及其校驗和。
- `alembic_version`: (由 Alembic 自動管理) 追蹤資料庫版本。

---

## 3. 開發與部署指南

### **階段一：環境設定與初始化**

1.  **安裝環境需求**:
    - 確保系統已安裝 Python 3.8+。
    - **SQLite**: 無需額外伺服器安裝，資料庫將是一個檔案。
    - **Redis**: 確保 Redis 服務正在運行。

2.  **建立並啟用 Python 虛擬環境**:
    - **目的**: 建立一個獨立的 Python 環境，避免與系統全域套件衝突，確保專案的穩定與可轉移性。
    - **建立**: 在專案根目錄下執行 `python3 -m venv venv`。
    - **啟用 (macOS/Linux)**: 執行 `source venv/bin/activate`。
    - **啟用 (Windows)**: 執行 `venv\Scripts\activate`。
    - *啟用後，您的終端機提示字元前會出現 `(venv)` 字樣。*

3.  **設定 `.env` 檔案**:
    - **目的**: 儲存敏感資訊，並與程式碼分離。
    - **步驟**: 建立 `.env` 檔案，並填寫 `REDIS_HOST`, `REDIS_PORT` 的值。
    - *注意: `.env` 檔案不應提交到版本控制系統。*

4.  **安裝相依套件**: 
    - 在虛擬環境中執行 `pip install -r requirements.txt`。

5.  **初始化資料庫**: 
    - **目的**: 根據 `database.py` 中定義的模型，建立 SQLite 資料庫檔案及所有必要的資料表。
    - **步驟**: 執行 `python database.py`。

6.  **設定專案檔案結構**: 
    - 確保已建立 `app.py`, `cli.py`, `config.ini`, `requirements.txt`, `database.py`, `data_loader.py`, `queries.py`, `auth.py` 檔案，以及 `pages/`, `tests/`, `setup_scripts/` 資料夾。

### **階段二：核心邏輯與測試**
- **任務 2.1**: 開發核心邏輯模組 (`database.py`, `data_loader.py`, `queries.py`, `auth.py`)。
- **任務 2.2**: 使用 Pytest 為核心邏輯編寫**單元測試**。

### **階段三：介面開發**
- **任務 3.1 (GUI)**: 開發 Streamlit 圖形化介面。
- **任務 3.2 (CLI)**: 開發 Typer 指令列介面。

### **階段四：整合與部署準備**
- **任務 4.1**: 完整測試 GUI 和 CLI 的所有功能。
- **任務 4.2**: 撰寫詳細的 `README.md` 文件，涵蓋所有設定、部署、使用及擴展的說明。