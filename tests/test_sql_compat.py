"""sql_compat 與依方言分支之查詢（SQLite in-memory 回歸）。"""
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, Job
from sql_compat import dialect_name, strftime_column, wait_seconds_between


@pytest.fixture
def memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


def test_dialect_name_sqlite(memory_db):
    assert dialect_name(memory_db) == "sqlite"


def test_strftime_column_sqlite_compiles(memory_db):
    expr = strftime_column(memory_db, "%Y-%m-%d", Job.start_time)
    compiled = str(
        memory_db.query(expr).statement.compile(dialect=memory_db.get_bind().dialect)
    )
    assert "strftime" in compiled.lower()


def test_wait_seconds_sqlite_compiles(memory_db):
    expr = wait_seconds_between(memory_db, Job.start_time, Job.queue_time)
    compiled = str(
        memory_db.query(expr).statement.compile(dialect=memory_db.get_bind().dialect)
    )
    assert "julianday" in compiled.lower()


def test_wait_seconds_scalar_sqlite(memory_db):
    memory_db.add(
        Job(
            job_id="w1",
            job_name="n",
            user_name="u",
            user_group="g",
            queue="q",
            job_status="C",
            nodes=1,
            cores=1,
            memory="1G",
            run_time_seconds=60,
            queue_time=datetime(2025, 1, 1, 10, 0, 0),
            start_time=datetime(2025, 1, 1, 10, 0, 30),
            elapse_limit_seconds=3600,
            resource_type="CPU",
            wallet_name=None,
            source_file="f.out",
        )
    )
    memory_db.commit()
    ws = wait_seconds_between(memory_db, Job.start_time, Job.queue_time)
    v = memory_db.query(ws).scalar()
    assert v is not None
    assert abs(float(v) - 30.0) < 1.0
