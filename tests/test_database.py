import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from database import Base, Job, User, Quota, GroupMapping, ProcessedFile

@pytest.fixture(scope="module")
def in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_tables_created(in_memory_db):
    # Check if tables exist by trying to query them
    assert in_memory_db.query(Job).count() == 0
    assert in_memory_db.query(User).count() == 0
    assert in_memory_db.query(Quota).count() == 0
    assert in_memory_db.query(GroupMapping).count() == 0
    assert in_memory_db.query(ProcessedFile).count() == 0

    # You can also check table names directly if needed
    inspector = inspect(in_memory_db.bind)
    assert "jobs" in inspector.get_table_names()
    assert "users" in inspector.get_table_names()
    assert "quotas" in inspector.get_table_names()
    assert "group_mappings" in inspector.get_table_names()
    assert "processed_files" in inspector.get_table_names()
