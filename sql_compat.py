"""
SQLite / PostgreSQL 日期與時間差表達式相容層（供 queries 使用）。

新增方言時須補齊此模組並跑完整測試。
"""
from __future__ import annotations

from sqlalchemy import Integer, String, cast, extract, func, literal_column
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement


def dialect_name(db: Session) -> str:
    return db.get_bind().dialect.name


# 僅涵蓋本專案實際使用的 strftime 第一參數
_SQLITE_STRFTIME_TO_PG = {
    "%Y-%m-%d": "YYYY-MM-DD",
    "%Y-%m": "YYYY-MM",
    "%Y": "YYYY",
    "%G": "IYYY",
    "%V": "IW",
}


def strftime_column(db: Session, sqlite_fmt: str, column) -> ColumnElement:
    """對應 SQLite strftime(fmt, col)；PostgreSQL 用 to_char。"""
    d = dialect_name(db)
    if d == "sqlite":
        return func.strftime(sqlite_fmt, column)
    if d == "postgresql":
        pg_fmt = _SQLITE_STRFTIME_TO_PG.get(sqlite_fmt)
        if pg_fmt is None:
            raise ValueError(
                f"strftime_column: 未對應的 SQLite 格式 {sqlite_fmt!r}，請補 sql_compat._SQLITE_STRFTIME_TO_PG"
            )
        return func.to_char(column, pg_fmt)
    raise NotImplementedError(f"不支援的資料庫方言: {d}")


def wait_seconds_between(db: Session, col_start, col_queue) -> ColumnElement:
    """排隊到開始的等待秒數（與原 julianday 差 * 86400 語意一致）。"""
    d = dialect_name(db)
    if d == "sqlite":
        return (func.julianday(col_start) - func.julianday(col_queue)) * 86400
    if d == "postgresql":
        return func.extract("epoch", col_start - col_queue)
    raise NotImplementedError(f"不支援的資料庫方言: {d}")


def day_of_week_zero_sunday_str(db: Session, column) -> ColumnElement:
    """週日=0 … 週六=6，型別為字串（與 SQLite strftime('%%w') 一致供 heatmap group）。"""
    d = dialect_name(db)
    if d == "sqlite":
        return func.strftime("%w", column)
    if d == "postgresql":
        return cast(cast(extract("dow", column), Integer), String)
    raise NotImplementedError(f"不支援的資料庫方言: {d}")


def iso_week_period_label(db: Session, column) -> ColumnElement:
    """週粒度標籤，如 2025-W03（ISO 週）。"""
    d = dialect_name(db)
    if d == "sqlite":
        return func.concat(
            func.strftime("%G", column),
            func.concat("-W", func.strftime("%V", column)),
        )
    if d == "postgresql":
        return func.concat(
            func.to_char(column, "IYYY"),
            "-W",
            func.to_char(column, "IW"),
        )
    raise NotImplementedError(f"不支援的資料庫方言: {d}")


def job_end_time_from_start_and_runtime(db: Session, start_col, run_seconds_col) -> ColumnElement:
    """start_time + run_time_seconds 的結束時間（供執行中作業篩選）。"""
    d = dialect_name(db)
    if d == "sqlite":
        return func.datetime(
            start_col,
            "+" + cast(run_seconds_col, String) + " seconds",
        )
    if d == "postgresql":
        return start_col + (run_seconds_col * literal_column("interval '1 second'"))
    raise NotImplementedError(f"不支援的資料庫方言: {d}")
