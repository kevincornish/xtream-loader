from database import SessionLocal, User
from main import get_password_hash


def create_admin_user(username, password):
    db = SessionLocal()
    hashed_password = get_password_hash(password)
    admin_user = User(username=username, hashed_password=hashed_password, is_admin=True)
    db.add(admin_user)
    db.commit()
    db.close()
    print(f"Admin user '{username}' created successfully.")


if __name__ == "__main__":
    username = input("Enter admin username: ")
    password = input("Enter admin password: ")
    create_admin_user(username, password)
