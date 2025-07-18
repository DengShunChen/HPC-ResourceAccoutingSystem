import pytest
import os
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base, Job, ProcessedFile, GroupMapping, User
from data_loader import calculate_checksum, transform_data, load_new_data, get_config
from unittest.mock import patch, MagicMock

@pytest.fixture(scope="module")
def in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

@pytest.fixture
def mock_config():
    with patch('data_loader.configparser.ConfigParser') as MockConfigParser:
        mock_config_instance = MockConfigParser.return_value
        mock_config_instance.get.side_effect = lambda section, option: {
            'data': {'log_directory_path': '/tmp/test_logs'},
            'log_schema': {'column_names': 'JobID,JobName,UserName,UserGroup,Queue,JobStatus,Nodes,Cores,Memory,RunTime,RunTimeSeconds,QueDateYear,QueDateMonth,QueDateDay,QueDateHour,QueDateMinute,QueDateSecond,StartDateYear,StartDateMonth,StartDateDay,StartDateHour,StartDateMinute,StartDateSecond,ElapseLimiteSecond'}
        }[section][option]
        yield mock_config_instance

@pytest.fixture
def dummy_log_file(tmp_path):
    log_dir = tmp_path / "test_logs"
    log_dir.mkdir()
    file_path = log_dir / "test_log_250716.out"
    content = (
        "job1 jobname1 user1 groupA queue1 status1 1 10 100G 100s 100 2025 07 16 10 00 00 2025 07 16 10 01 40 3600\n"
        "job2 jobname2 user2 groupB queue2 status2 2 20 200G 200s 200 2025 07 16 10 05 00 2025 07 16 10 08 20 7200\n"
        "job3 jobname3 user3 groupA queue1 status3 1 5 50G 50s 50 2025 07 16 10 10 00 2025 07 16 10 11 00 1800\n"
    )
    file_path.write_text(content)
    return file_path

def test_calculate_checksum(dummy_log_file):
    checksum = calculate_checksum(dummy_log_file)
    assert isinstance(checksum, str)
    assert len(checksum) == 64  # SHA256 produces a 64-character hex string

def test_transform_data(in_memory_db):
    # Create a dummy DataFrame matching the expected raw format
    raw_data = {
        'JobID': ['job1', 'job2'],
        'JobName': ['name1', 'name2'],
        'UserName': ['user1', 'user2'],
        'UserGroup': ['groupA', 'groupB'],
        'Queue': ['cpu_queue', 'gpu_queue'],
        'JobStatus': ['R', 'C'],
        'Nodes': [1, 2],
        'Cores': [10, 20],
        'Memory': ['100G', '200G'],
        'RunTime': ['100s', '200s'],
        'RunTimeSeconds': [100, 200],
        'QueDateYear': [2025, 2025],
        'QueDateMonth': [7, 7],
        'QueDateDay': [16, 16],
        'QueDateHour': [10, 10],
        'QueDateMinute': [0, 5],
        'QueDateSecond': [0, 0],
        'StartDateYear': [2025, 2025],
        'StartDateMonth': [7, 7],
        'StartDateDay': [16, 16],
        'StartDateHour': [10, 10],
        'StartDateMinute': [1, 8],
        'StartDateSecond': [40, 20],
        'ElapseLimiteSecond': [3600, 7200]
    }
    raw_df = pd.DataFrame(raw_data)
    raw_df['source_file'] = 'test_file.out' # Add source_file for testing

    # Add a group mapping for testing
    user_for_mapping = User(username="mapped_user", hashed_password="hashed", role="user")
    in_memory_db.add(user_for_mapping)
    in_memory_db.commit()
    in_memory_db.refresh(user_for_mapping)
    in_memory_db.add(GroupMapping(source_group="groupA", target_user_id=user_for_mapping.id))
    in_memory_db.commit()

    transformed_df = transform_data(raw_df, in_memory_db)

    assert 'job_id' in transformed_df.columns
    assert 'queue_time' in transformed_df.columns
    assert 'start_time' in transformed_df.columns
    assert 'resource_type' in transformed_df.columns
    assert transformed_df['resource_type'].iloc[0] == 'CPU'
    assert transformed_df['resource_type'].iloc[1] == 'GPU'
    assert transformed_df['user_name'].iloc[0] == 'mapped_user' # Check if mapping applied
    assert transformed_df['user_name'].iloc[1] == 'user2' # Check if unmapped user remains

def test_load_new_data(in_memory_db, dummy_log_file, mock_config):
    # Mock os.listdir to return our dummy file
    with patch('os.listdir', return_value=[os.path.basename(dummy_log_file)]) as mock_listdir:
        with patch('os.path.join', return_value=str(dummy_log_file)):
            load_new_data(db=in_memory_db)

            # Verify data was loaded
            assert in_memory_db.query(Job).count() == 3
            assert in_memory_db.query(ProcessedFile).count() == 1
            assert in_memory_db.query(ProcessedFile).first().filename == os.path.basename(dummy_log_file)

            # Run again to ensure it doesn't process the same file twice
            load_new_data(db=in_memory_db)
            assert in_memory_db.query(Job).count() == 3 # Should still be 3 jobs
            assert in_memory_db.query(ProcessedFile).count() == 1 # Should still be 1 processed file
