import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, Job
from database_utils import (
    validate_query_for_explain,
    explain_query_plan,
    analyze_database,
    vacuum_database,
)


@pytest.fixture
def memory_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


def test_validate_query_for_explain_accepts_select():
    assert validate_query_for_explain("SELECT 1") is None
    assert validate_query_for_explain("  select * from jobs ") is None


def test_validate_query_for_explain_rejects_non_select():
    assert validate_query_for_explain("DELETE FROM jobs") is not None
    assert validate_query_for_explain("UPDATE jobs SET id=1") is not None


def test_validate_query_for_explain_rejects_semicolon():
    assert validate_query_for_explain("SELECT 1; SELECT 2") is not None


def test_explain_query_plan_on_memory_db(memory_session):
    memory_session.add(
        Job(
            job_id="e1",
            job_name="n",
            user_name="u",
            user_group="g",
            queue="q",
            job_status="C",
            nodes=1,
            cores=1,
            memory="1G",
            run_time_seconds=1,
            queue_time=None,
            start_time=None,
            elapse_limit_seconds=1,
            resource_type="CPU",
        )
    )
    memory_session.commit()

    plan = explain_query_plan("SELECT * FROM jobs WHERE job_id = 'e1'", memory_session)
    assert "error" not in plan[0]
    assert any("jobs" in (step.get("detail") or "").lower() for step in plan)


def test_analyze_database_memory(memory_session):
    out = analyze_database(memory_session)
    assert out["status"] == "success"


def test_vacuum_database_file(tmp_path, monkeypatch):
    """VACUUM 在檔案庫上應成功（使用獨立 engine 模組會綁定預設 DATABASE_FILE，改為 monkeypatch）。"""
    import database as dbmod
    import database_utils as du

    dbfile = tmp_path / "t.db"
    monkeypatch.setattr(dbmod, "DATABASE_FILE", str(dbfile))
    monkeypatch.setattr(dbmod, "DATABASE_URL", f"sqlite:///{dbfile}")
    monkeypatch.setattr(du, "DATABASE_FILE", str(dbfile))

    new_engine = create_engine(
        f"sqlite:///{dbfile}",
        connect_args={"check_same_thread": False, "timeout": 5.0},
    )
    monkeypatch.setattr(du, "engine", new_engine)
    Base.metadata.create_all(new_engine)

    result = vacuum_database()
    assert result["status"] == "success"
