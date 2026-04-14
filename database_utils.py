"""
Database utility functions for maintenance and optimization.
Provides functions for ANALYZE, VACUUM, and database statistics.
"""
import os
import re
from sqlalchemy import text, inspect
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Dict, List, Any, Optional

from database import engine, DATABASE_FILE, SessionLocal

_EXPLAIN_SELECT_PREFIX = re.compile(r"^\s*select\b", re.IGNORECASE | re.DOTALL)
_EXPLAIN_FORBIDDEN = re.compile(
    r"\b(attach|pragma|vacuum|reindex|detach)\b",
    re.IGNORECASE,
)


def validate_query_for_explain(query_sql: str) -> Optional[str]:
    """Return error message if query is not allowed for EXPLAIN, else None."""
    q = (query_sql or "").strip()
    if not q:
        return "查詢不可為空"
    if len(q) > 8192:
        return "查詢長度超過上限（8192 字元）"
    if ";" in q:
        return "不允許含分號或多重語句"
    if not _EXPLAIN_SELECT_PREFIX.match(q):
        return "僅允許以 SELECT 開頭的查詢"
    if _EXPLAIN_FORBIDDEN.search(q):
        return "查詢含有不允許的關鍵字（例如 PRAGMA、ATTACH）"
    return None


def analyze_database(db: Optional[Session] = None) -> Dict[str, Any]:
    """
    Execute ANALYZE to update query optimizer statistics.

    Args:
        db: Optional database session. If None, creates a new connection.

    Returns:
        Dictionary with execution results and timing information.
    """
    close_session = False
    if db is None:
        db = SessionLocal()
        close_session = True

    try:
        start_time = datetime.now()

        db.execute(text("ANALYZE;"))
        db.commit()

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        return {
            "status": "success",
            "operation": "ANALYZE",
            "duration_seconds": duration,
            "timestamp": end_time.isoformat(),
        }
    except Exception as e:
        db.rollback()
        return {
            "status": "error",
            "operation": "ANALYZE",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }
    finally:
        if close_session:
            db.close()


def vacuum_database() -> Dict[str, Any]:
    """
    Execute VACUUM to reorganize the database and reclaim unused space.

    SQLite VACUUM must run outside a transaction; this uses an AUTOCOMMIT connection.

    Returns:
        Dictionary with execution results and timing information.

    Note:
        VACUUM can take a long time on large databases and needs exclusive access.
    """
    try:
        start_time = datetime.now()

        db_size_before = os.path.getsize(DATABASE_FILE) if os.path.exists(DATABASE_FILE) else 0

        engine.dispose()
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text("VACUUM"))

        db_size_after = os.path.getsize(DATABASE_FILE) if os.path.exists(DATABASE_FILE) else 0

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        return {
            "status": "success",
            "operation": "VACUUM",
            "duration_seconds": duration,
            "size_before_bytes": db_size_before,
            "size_after_bytes": db_size_after,
            "size_reclaimed_bytes": db_size_before - db_size_after,
            "timestamp": end_time.isoformat(),
        }
    except Exception as e:
        return {
            "status": "error",
            "operation": "VACUUM",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }


def get_database_stats(db: Session = None) -> Dict[str, Any]:
    """
    Get comprehensive database statistics including table sizes, row counts, and index information.

    Args:
        db: Optional database session. If None, creates a new connection.

    Returns:
        Dictionary with database statistics.
    """
    close_session = False
    if db is None:
        db = SessionLocal()
        close_session = True

    try:
        try:
            db.execute(text("PRAGMA busy_timeout = 5000;"))
            db.commit()
        except Exception:
            pass

        stats = {
            "database_file": DATABASE_FILE,
            "database_size_bytes": os.path.getsize(DATABASE_FILE) if os.path.exists(DATABASE_FILE) else 0,
            "tables": {},
            "indexes": {},
            "pragmas": {},
            "timestamp": datetime.now().isoformat(),
        }

        pragma_settings = [
            "cache_size",
            "page_size",
            "temp_store",
            "synchronous",
            "locking_mode",
            "journal_mode",
            "foreign_keys",
            "busy_timeout",
        ]
        for pragma in pragma_settings:
            try:
                result = db.execute(text(f"PRAGMA {pragma};")).fetchone()
                if result:
                    stats["pragmas"][pragma] = result[0]
            except Exception:
                pass

        inspector = inspect(engine)
        tables = inspector.get_table_names()

        for table_name in tables:
            try:
                # table_name 來自 inspector；以雙引號包住避免保留字問題
                row_count_result = db.execute(text(f'SELECT COUNT(*) FROM "{table_name}";')).fetchone()
                row_count = row_count_result[0] if row_count_result else 0

                stats["tables"][table_name] = {
                    "row_count": row_count,
                    "columns": inspector.get_columns(table_name),
                }

                indexes = inspector.get_indexes(table_name)
                if indexes:
                    stats["indexes"][table_name] = [
                        {
                            "name": idx["name"],
                            "columns": idx["column_names"],
                            "unique": idx.get("unique", False),
                        }
                        for idx in indexes
                    ]
            except Exception as e:
                stats["tables"][table_name] = {"error": str(e)}

        try:
            page_count_result = db.execute(text("PRAGMA page_count;")).fetchone()
            page_size_result = db.execute(text("PRAGMA page_size;")).fetchone()
            if page_count_result and page_size_result:
                stats["database_pages"] = page_count_result[0]
                stats["page_size_bytes"] = page_size_result[0]
                stats["calculated_size_bytes"] = page_count_result[0] * page_size_result[0]
        except Exception:
            pass

        return stats
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }
    finally:
        if close_session:
            db.close()


def explain_query_plan(query_sql: str, db: Session = None) -> List[Dict[str, Any]]:
    """
    Execute EXPLAIN QUERY PLAN to analyze a SQL query's execution plan.

    Args:
        query_sql: SQL query string to analyze (SELECT only).
        db: Optional database session. If None, creates a new connection.

    Returns:
        List of dictionaries containing query plan information.
    """
    validation_error = validate_query_for_explain(query_sql)
    if validation_error:
        return [{"error": validation_error}]

    close_session = False
    if db is None:
        db = SessionLocal()
        close_session = True

    try:
        explain_query = f"EXPLAIN QUERY PLAN {query_sql}"
        result = db.execute(text(explain_query)).fetchall()

        plan = []
        for row in result:
            plan.append(
                {
                    "selectid": row[0] if len(row) > 0 else None,
                    "order": row[1] if len(row) > 1 else None,
                    "from": row[2] if len(row) > 2 else None,
                    "detail": row[3] if len(row) > 3 else None,
                }
            )

        return plan
    except Exception as e:
        return [{"error": str(e)}]
    finally:
        if close_session:
            db.close()


def format_size(size_bytes: int) -> str:
    """
    Format file size in human-readable format.

    Args:
        size_bytes: Size in bytes.

    Returns:
        Formatted size string (e.g., "1.5 GB").
    """
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"
