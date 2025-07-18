import pytest
import os
from datetime import datetime, timedelta, date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base, Job, User, Quota, GroupMapping
from queries import get_kpi_data, get_usage_over_time, get_filtered_jobs, get_all_users, get_all_groups, get_all_queues,     get_all_registered_users, get_user_quota, set_user_quota, delete_user, get_all_group_mappings, add_group_mapping, delete_group_mapping,     generate_accounting_report
from unittest.mock import patch, MagicMock
import pandas as pd

@pytest.fixture(scope="module")
def in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

@pytest.fixture(autouse=True)
def mock_redis_client():
    with patch('queries.redis_client') as mock_redis:
        mock_redis.get.return_value = None  # Simulate cache miss by default
        mock_redis.setex.return_value = True # Simulate successful set
        yield mock_redis

@pytest.fixture
def populate_jobs(in_memory_db):
    jobs_data = [
        Job(job_id="job1", job_name="test_job_1", user_name="userA", user_group="groupX", queue="cpu_queue",
            job_status="COMPLETED", nodes=1, cores=10, memory="10G", run_time_str="100s", run_time_seconds=100,
            queue_time=datetime(2025, 7, 1, 10, 0, 0), start_time=datetime(2025, 7, 1, 10, 1, 0), elapse_limit_seconds=3600, resource_type="CPU"),
        Job(job_id="job2", job_name="test_job_2", user_name="userB", user_group="groupY", queue="gpu_queue",
            job_status="COMPLETED", nodes=1, cores=20, memory="20G", run_time_str="200s", run_time_seconds=200,
            queue_time=datetime(2025, 7, 1, 11, 0, 0), start_time=datetime(2025, 7, 1, 11, 2, 0), elapse_limit_seconds=7200, resource_type="GPU"),
        Job(job_id="job3", job_name="test_job_3", user_name="userA", user_group="groupX", queue="cpu_queue",
            job_status="RUNNING", nodes=2, cores=5, memory="5G", run_time_str="50s", run_time_seconds=50,
            queue_time=datetime(2025, 7, 2, 9, 0, 0), start_time=datetime(2025, 7, 2, 9, 1, 0), elapse_limit_seconds=1800, resource_type="CPU"),
        Job(job_id="job4", job_name="test_job_4", user_name="userC", user_group="groupZ", queue="cpu_queue",
            job_status="COMPLETED", nodes=1, cores=15, memory="15G", run_time_str="150s", run_time_seconds=150,
            queue_time=datetime(2025, 7, 3, 14, 0, 0), start_time=datetime(2025, 7, 3, 14, 5, 0), elapse_limit_seconds=5400, resource_type="CPU"),
    ]
    in_memory_db.add_all(jobs_data)
    in_memory_db.commit()

    # Add some users for admin tests
    users_data = [
        User(username="admin_user", hashed_password="hashed_admin_password", role="admin"),
        User(username="normal_user", hashed_password="hashed_normal_password", role="user"),
    ]
    in_memory_db.add_all(users_data)
    in_memory_db.commit()

    yield
    # Clean up after tests
    in_memory_db.query(Job).delete()
    in_memory_db.query(User).delete()
    in_memory_db.query(Quota).delete()
    in_memory_db.query(GroupMapping).delete()
    in_memory_db.commit()

def test_get_kpi_data(in_memory_db, populate_jobs):
    start_date = date(2025, 7, 1)
    end_date = date(2025, 7, 3)
    kpis = get_kpi_data(in_memory_db, start_date, end_date)

    assert kpis['CPU']['total_node_hours'] > 0
    assert kpis['GPU']['total_core_hours'] > 0
    assert kpis['overall_total_jobs'] == 4

def test_get_usage_over_time(in_memory_db, populate_jobs):
    start_date = date(2025, 7, 1)
    end_date = date(2025, 7, 3)
    usage_data = get_usage_over_time(in_memory_db, start_date, end_date)
    assert len(usage_data) > 0
    assert any(d['date'] == '2025-07-01' for d in usage_data)

def test_get_filtered_jobs(in_memory_db, populate_jobs):
    jobs_page1 = get_filtered_jobs(in_memory_db, page=1, page_size=2)
    assert jobs_page1['total_items'] == 4
    assert len(jobs_page1['jobs']) == 2

    jobs_filtered = get_filtered_jobs(in_memory_db, user_name="userA")
    assert jobs_filtered['total_items'] == 2

def test_get_all_users_groups_queues(in_memory_db, populate_jobs):
    users = get_all_users(in_memory_db)
    assert "userA" in users
    assert "userB" in users
    assert "admin_user" in users # From registered users

    groups = get_all_groups(in_memory_db)
    assert "groupX" in groups

    queues = get_all_queues(in_memory_db)
    assert "cpu_queue" in queues

# Admin Panel Tests
def test_get_all_registered_users(in_memory_db, populate_jobs):
    users = get_all_registered_users(in_memory_db)
    assert len(users) == 2 # admin_user and normal_user
    assert any(u['username'] == "admin_user" for u in users)

def test_set_and_get_user_quota(in_memory_db, populate_jobs):
    user = in_memory_db.query(User).filter(User.username == "normal_user").first()
    assert user is not None

    set_user_quota(in_memory_db, user.id, 100.0, 50.0, "monthly")
    quota = get_user_quota(in_memory_db, user.id)
    assert quota.cpu_core_hours_limit == 100.0
    assert quota.gpu_core_hours_limit == 50.0

    # Update quota
    set_user_quota(in_memory_db, user.id, 120.0, 60.0, "monthly")
    quota = get_user_quota(in_memory_db, user.id)
    assert quota.cpu_core_hours_limit == 120.0

def test_add_and_delete_group_mapping(in_memory_db, populate_jobs):
    user = in_memory_db.query(User).filter(User.username == "normal_user").first()
    assert user is not None

    add_group_mapping(in_memory_db, "new_group", user.username)
    mappings = get_all_group_mappings(in_memory_db)
    assert any(m['source_group'] == "new_group" and m['target_username'] == "normal_user" for m in mappings)

    mapping_id = [m['id'] for m in mappings if m['source_group'] == "new_group"][0]
    delete_group_mapping(in_memory_db, mapping_id)
    mappings_after_delete = get_all_group_mappings(in_memory_db)
    assert not any(m['source_group'] == "new_group" for m in mappings_after_delete)

def test_delete_user(in_memory_db, populate_jobs):
    user_to_delete = in_memory_db.query(User).filter(User.username == "normal_user").first()
    assert user_to_delete is not None
    user_id = user_to_delete.id

    # Add a quota and mapping for this user to ensure they are deleted
    set_user_quota(in_memory_db, user_id, 10, 10)
    add_group_mapping(in_memory_db, "temp_group", user_to_delete.username)
    in_memory_db.commit()

    delete_user(in_memory_db, user_id)
    assert in_memory_db.query(User).filter(User.id == user_id).first() is None
    assert in_memory_db.query(Quota).filter(Quota.user_id == user_id).first() is None
    assert in_memory_db.query(GroupMapping).filter(GroupMapping.target_user_id == user_id).first() is None

def test_generate_accounting_report(in_memory_db, populate_jobs):
    report = generate_accounting_report(in_memory_db, year=2025, month="2025-07", user_name="userA")
    assert isinstance(report, pd.DataFrame)
    assert not report.empty
    assert len(report) == 2 # userA has 2 jobs in July 2025
