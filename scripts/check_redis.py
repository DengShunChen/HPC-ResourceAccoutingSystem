#!/usr/bin/env python3
"""
Redis 連線與延遲自檢（與 queries.redis_client 相同環境變數與逾時）。

用法:
  python scripts/check_redis.py
  # 或專案 venv:
  ./venv/bin/python scripts/check_redis.py

環境變數（與 queries.py 一致）:
  REDIS_HOST   預設 localhost
  REDIS_PORT   預設 6379

選用（僅本腳本；queries.py 尚未使用時請改程式或改走無密碼本機）:
  REDIS_PASSWORD
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
os.chdir(_ROOT)

from dotenv import load_dotenv

load_dotenv()

import redis


def _client() -> redis.Redis:
    host = os.getenv("REDIS_HOST", "localhost")
    port = int(os.getenv("REDIS_PORT", "6379"))
    kw: dict = {
        "host": host,
        "port": port,
        "db": 0,
        "decode_responses": True,
        "socket_connect_timeout": 1.5,
        "socket_timeout": 3.0,
    }
    pw = (os.getenv("REDIS_PASSWORD") or "").strip()
    if pw:
        kw["password"] = pw
    return redis.Redis(**kw)


def main() -> int:
    host = os.getenv("REDIS_HOST", "localhost")
    port = int(os.getenv("REDIS_PORT", "6379"))
    print("=== Redis 自檢 ===\n")
    print(f"REDIS_HOST={host!r} REDIS_PORT={port}")
    if (os.getenv("REDIS_PASSWORD") or "").strip():
        print("REDIS_PASSWORD=（已設定，不顯示內容；僅本腳本會傳給 redis-py）")
    print(
        "逾時: connect 1.5s / read 3.0s（與 queries.py 相同）\n"
        "注意: 應用程式 queries 目前未讀 REDIS_PASSWORD；需密碼時要改 queries 或本機無密碼。\n"
    )

    try:
        r = _client()
    except Exception as e:
        print(f"建立 Redis 客戶端失敗: {e}")
        return 2

    # PING + 延遲
    try:
        t0 = time.perf_counter()
        pong = r.ping()
        dt_ms = (time.perf_counter() - t0) * 1000
        print(f"PING -> {pong!r}   往返約 {dt_ms:.1f} ms")
    except redis.exceptions.TimeoutError as e:
        print(f"PING 逾時（socket_connect_timeout / socket_timeout）: {e}")
        return 1
    except redis.exceptions.ConnectionError as e:
        print(f"無法連線（服務未開、防火牆、主機錯）: {e}")
        return 1
    except redis.exceptions.AuthenticationError as e:
        print(f"認證失敗（需要密碼或 ACL）: {e}")
        return 1
    except redis.exceptions.RedisError as e:
        print(f"PING 失敗: {e}")
        return 1

    # 與報表快取相關的鍵（只讀）
    gen_key = "report_cache_gen"
    try:
        g = r.get(gen_key)
        print(f"GET {gen_key!r} -> {g!r}")
    except redis.exceptions.RedisError as e:
        print(f"GET {gen_key}: {e}")

    # 輕量寫入測試（短 TTL，不影響業務鍵名空間外）
    test_key = "hpc_redis_selftest"
    try:
        t0 = time.perf_counter()
        r.setex(test_key, 5, "ok")
        v = r.get(test_key)
        r.delete(test_key)
        dt_ms = (time.perf_counter() - t0) * 1000
        print(f"SETEX/GET/DEL {test_key!r} -> {v!r}   合計約 {dt_ms:.1f} ms")
    except redis.exceptions.RedisError as e:
        print(f"寫入測試失敗（唯讀帳號或權限）: {e}")
        return 1

    # INFO（部分雲端會關；失敗不當成錯誤）
    try:
        info = r.info("server")
        ver = info.get("redis_version", "?")
        role = info.get("role", "?")
        print(f"INFO server: redis_version={ver!r} role={role!r}")
    except redis.exceptions.RedisError as e:
        print(f"INFO server 略過: {e}")

    print("\n結論: Redis 連線與基本讀寫正常。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
