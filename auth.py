from passlib.context import CryptContext
from database import SessionLocal, User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_user(db: SessionLocal, username: str):
    return db.query(User).filter(User.username == username).first()

def create_user(db: SessionLocal, username: str, password: str, role: str = "user"):
    hashed_password = get_password_hash(password)
    db_user = User(username=username, hashed_password=hashed_password, role=role)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def authenticate_user(db: SessionLocal, username: str, password: str):
    user = get_user(db, username)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user

# --- Initial Admin User Creation (for CLI or initial setup) ---
def create_initial_admin_user(db: SessionLocal, admin_username: str, admin_password: str):
    if not get_user(db, admin_username):
        print(f"Creating initial admin user: {admin_username}")
        create_user(db, admin_username, admin_password, role="admin")
        print("Initial admin user created successfully.")
    else:
        print(f"Admin user '{admin_username}' already exists.")

if __name__ == "__main__":
    # This block is for initial setup via CLI
    db = SessionLocal()
    try:
        admin_username = input("Enter initial admin username: ")
        admin_password = input("Enter initial admin password: ")
        create_initial_admin_user(db, admin_username, admin_password)
    finally:
        db.close()
