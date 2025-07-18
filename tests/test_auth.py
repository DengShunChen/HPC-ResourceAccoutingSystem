import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base, User
from auth import get_password_hash, verify_password, create_user, get_user, authenticate_user

@pytest.fixture(scope="module")
def in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_password_hashing():
    password = "test_password"
    hashed_password = get_password_hash(password)
    assert verify_password(password, hashed_password)
    assert not verify_password("wrong_password", hashed_password)

def test_create_and_get_user(in_memory_db):
    username = "testuser"
    password = "testpassword"
    user = create_user(in_memory_db, username, password)
    assert user.username == username
    assert user.role == "user"

    retrieved_user = get_user(in_memory_db, username)
    assert retrieved_user.username == username

def test_authenticate_user(in_memory_db):
    username = "authuser"
    password = "authpassword"
    create_user(in_memory_db, username, password)

    authenticated_user = authenticate_user(in_memory_db, username, password)
    assert authenticated_user.username == username

    # Test with wrong password
    assert authenticate_user(in_memory_db, username, "wrongpassword") is False

    # Test with non-existent user
    assert authenticate_user(in_memory_db, "nonexistent", "password") is False
