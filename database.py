import os
from sqlalchemy import create_engine, Column, Integer, String, DateTime, BigInteger, Float, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from dotenv import load_dotenv
from sqlalchemy import text # Moved to top

# Load environment variables from .env file for sensitive data
load_dotenv()

# --- Database Connection ---
# For SQLite, the database is a file. We'll store it in the project root.
DATABASE_FILE = os.getenv("DATABASE_FILE", "./resource_accounting.db")
DATABASE_URL = f"sqlite:///{DATABASE_FILE}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Enable WAL mode for better concurrency
with engine.connect() as connection:
    connection.execute(text("PRAGMA journal_mode=WAL;"))
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

# This function can be called to create all tables
def create_all_tables():
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    print("Creating database tables...")
    create_all_tables()
    print("Tables created successfully.")