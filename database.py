import os
from contextlib import contextmanager

from sqlalchemy import create_engine, Column, Integer, String, DateTime, BigInteger, Float, Boolean, ForeignKey, Index
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.pool import NullPool
from dotenv import load_dotenv
from sqlalchemy import text # Moved to top

# Load environment variables from .env file for sensitive data
load_dotenv()

# --- Database Connection ---
# For SQLite, the database is a file. We'll store it in the project root.
DATABASE_FILE = os.getenv("DATABASE_FILE", "./resource_accounting.db")
DATABASE_URL = f"sqlite:///{DATABASE_FILE}"

# SQLite 檔案庫：使用 NullPool 避免不適用的小連線池堆疊；每次請求新連線、用完即關
engine = create_engine(
    DATABASE_URL,
    connect_args={
        "check_same_thread": False,
        "timeout": 5.0  # SQLite busy timeout in seconds (helps with concurrent access)
    },
    pool_pre_ping=True,
    poolclass=NullPool,
    echo=False  # Set to False in production
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Optimize SQLite PRAGMA settings for better performance
with engine.connect() as connection:
    # Busy timeout: wait up to 5 seconds for locks (helps with concurrent access)
    connection.execute(text("PRAGMA busy_timeout = 5000;"))
    # Cache size: 64MB (negative value means KB)
    connection.execute(text("PRAGMA cache_size = -65536;"))
    # Temporary database stored in memory for better performance
    connection.execute(text("PRAGMA temp_store = MEMORY;"))
    # Synchronous mode: balance between performance and safety
    connection.execute(text("PRAGMA synchronous = NORMAL;"))
    # Locking mode: NORMAL for better concurrency (WAL mode handles concurrency better)
    connection.execute(text("PRAGMA locking_mode = NORMAL;"))
    # Journal mode: WAL for better read/write concurrency
    connection.execute(text("PRAGMA journal_mode = WAL;"))
    # Foreign keys support
    connection.execute(text("PRAGMA foreign_keys = ON;"))
    connection.commit()
Base = declarative_base()

# --- Database Models ---

class Job(Base):
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String, index=True, unique=True)
    job_name = Column(String)
    user_name = Column(String, index=True)
    user_group = Column(String, index=True)
    queue = Column(String, index=True)
    job_status = Column(String)
    nodes = Column(Integer)
    cores = Column(Integer)
    memory = Column(String) # Keeping as string to handle various formats like '100G', '500M'
    run_time_seconds = Column(BigInteger)
    queue_time = Column(DateTime)
    start_time = Column(DateTime)
    elapse_limit_seconds = Column(BigInteger)
    resource_type = Column(String, index=True) # 'CPU' or 'GPU'
    wallet_name = Column(String, index=True, nullable=True) # New column for wallet name
    source_file = Column(String, index=True) # Added to track the source of the job data
    
    # Indexes (aligned with Alembic migration c5892216; avoid duplicate index=True on columns)
    __table_args__ = (
        Index('ix_jobs_start_time', 'start_time'),
        Index('ix_jobs_queue_time', 'queue_time'),
        Index('ix_jobs_start_time_resource_type', 'start_time', 'resource_type'),
        # Index for time range queries with wallet
        Index('ix_jobs_start_time_wallet_name', 'start_time', 'wallet_name'),
        # Index for time range queries with user
        Index('ix_jobs_start_time_user_name', 'start_time', 'user_name'),
        # Index for multi-dimensional queries
        Index('ix_jobs_start_time_user_group_resource_type', 'start_time', 'user_group', 'resource_type'),
        # Covering index for aggregation queries (includes commonly aggregated columns)
        Index('ix_jobs_start_time_resource_type_metrics', 'start_time', 'resource_type', 'run_time_seconds', 'nodes', 'cores'),
        # Index for queue time queries
        Index('ix_jobs_queue_time_start_time', 'queue_time', 'start_time'),
    )

class Wallet(Base):
    __tablename__ = "wallets"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    description = Column(String, nullable=True)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String, default="user") # 'user' or 'admin'

class Quota(Base):
    __tablename__ = "quotas"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), index=True) # Added ForeignKey
    cpu_core_hours_limit = Column(Float)
    gpu_core_hours_limit = Column(Float)
    period = Column(String) # e.g., 'monthly', 'quarterly'
    user = relationship("User") # Added relationship

class GroupMapping(Base):
    __tablename__ = "group_mappings"
    id = Column(Integer, primary_key=True, index=True)
    source_group = Column(String, unique=True, index=True)
    target_user_id = Column(Integer, ForeignKey('users.id'), index=True) # Added ForeignKey
    target_user = relationship("User") # Added relationship

class ProcessedFile(Base):
    __tablename__ = "processed_files"
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, unique=True, index=True)
    checksum = Column(String)

class GroupToGroupMapping(Base):
    __tablename__ = "group_to_group_mappings"
    id = Column(Integer, primary_key=True, index=True)
    source_group = Column(String, unique=True, index=True)
    target_group = Column(String, index=True)

class GroupToWalletMapping(Base):
    __tablename__ = "group_to_wallet_mappings"
    id = Column(Integer, primary_key=True, index=True)
    source_group = Column(String, unique=True, index=True)
    wallet_id = Column(Integer, ForeignKey('wallets.id'))
    wallet = relationship("Wallet")

class UserToWalletMapping(Base):
    __tablename__ = "user_to_wallet_mappings"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), unique=True, index=True) # Added ForeignKey
    wallet_id = Column(Integer, ForeignKey('wallets.id'))
    wallet = relationship("Wallet")
    user = relationship("User") # Added relationship

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def db_session_scope():
    """非產生器版 Session，供 Streamlit 等以 `with db_session_scope() as db:` 確保 close。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# This function can be called to create all tables
def create_all_tables():
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    print("Creating database tables...")
    create_all_tables()
    print("Tables created successfully.")
