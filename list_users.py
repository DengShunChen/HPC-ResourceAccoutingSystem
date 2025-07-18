from database import SessionLocal
from queries import get_all_registered_users

db = SessionLocal()
try:
    users = get_all_registered_users(db)
    if users:
        print("Registered Users:")
        for user in users:
            print(f"- Username: {user['username']}, Role: {user['role']}, ID: {user['id']}")
    else:
        print("No registered users found.")
finally:
    db.close()