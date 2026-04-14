#!/usr/bin/env python3
"""
簡易資料庫負載與環境診斷：協助區分 I/O、查詢時間與（SQLite）鎖競爭。

用法（建議在專案 venv 下）:
  python scripts/profile_database.py

若需對照多次載入或儀表操作，可在變更前後各執行一次比對輸出。
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

# 專案根目錄
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.chdir(_ROOT)

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from database import DATABASE_FILE, DATABASE_URL, SessionLocal, engine, Job


def _sqlite_file_path() -> str:
    if engine.dialect.name != "sqlite":
        return ""
    if DATABASE_FILE:
        return DATABASE_FILE
    try:
        return str(engine.url.database) if engine.url.database else ""
    except Exception:
        return ""


def _mask_url(url: str) -> str:
    try:
        p = urlparse(url)
        if p.password:
            netloc = f"{p.username}:***@{p.hostname or ''}"
            if p.port:
                netloc += f":{p.port}"
            return p._replace(netloc=netloc).geturl()
    except Exception:
        pass
    return url


def _mount_hint_for_path(path: str) -> str:
    """Linux：嘗試對照 /proc/mounts 推測檔案所在掛載點（僅提示，非嚴格證明）。"""
    if not path or not os.path.isfile(path):
        return "（非本機一般檔案或不存在）"
    mounts = Path("/proc/mounts")
    if not mounts.is_file():
        return "（無 /proc/mounts，略過掛載提示）"
    best = ""
    abspath = os.path.realpath(path)
    for line in mounts.read_text().splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        mnt = parts[1]
        if abspath.startswith(mnt + os.sep) and len(mnt) > len(best):
            best = mnt
    if best:
        return f"路徑前綴符合掛載點: {best}（常見：NFS 上 SQLite 易有鎖／延遲）"
    return "無法從 /proc/mounts 對應掛載點"


def main() -> None:
    print("=== HPC-ResourceAccoutingSystem DB profile ===\n")
    print("ENGINE_DIALECT:", engine.dialect.name)
    print("DATABASE_URL: ", _mask_url(DATABASE_URL))
    sqlite_path = _sqlite_file_path()
    if engine.dialect.name == "sqlite" and sqlite_path:
        print("SQLite 檔案路徑:", sqlite_path)
        if os.path.isfile(sqlite_path):
            print("DB 檔大小 (bytes):", os.path.getsize(sqlite_path))
            print(_mount_hint_for_path(sqlite_path))
        else:
            print("（SQLite 檔尚未建立）")

    db: Session = SessionLocal()
    try:
        t0 = time.perf_counter()
        n = db.query(func.count(Job.id)).scalar() or 0
        t1 = time.perf_counter()
        print(f"\nCOUNT(jobs.id): {n}  耗時: {(t1 - t0) * 1000:.1f} ms")

        t0 = time.perf_counter()
        db.execute(text("SELECT 1"))
        t1 = time.perf_counter()
        print(f"SELECT 1 (round-trip): {(t1 - t0) * 1000:.1f} ms")

        if n > 0:
            t0 = time.perf_counter()
            _ = (
                db.query(func.min(Job.start_time), func.max(Job.start_time))
                .select_from(Job)
                .one()
            )
            t1 = time.perf_counter()
            print(f"MIN/MAX(start_time): {(t1 - t0) * 1000:.1f} ms")
    finally:
        db.close()

    print(
        "\n--- 如何解讀 ---\n"
        "• COUNT / MINMAX 明顯偏慢且 DB 在網路檔案系統：多半是 **磁碟 I/O / 鎖**。\n"
        "• 僅 Streamlit 儀表慢、此處快：瓶頸可能在 **Redis、Python 聚合、或查詢未命中索引**。\n"
        "• 多人同時 **寫入** 同一 SQLite 檔：易 **database is locked**；可改檔案位置或改用伺服器 DB。\n"
    )


if __name__ == "__main__":
    main()
