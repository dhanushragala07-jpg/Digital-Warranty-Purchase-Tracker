import os
from sqlalchemy import select
from main import SessionLocal, User, password_hash

email = os.getenv("ADMIN_EMAIL", "").strip().lower()
name = os.getenv("ADMIN_NAME", "Administrator").strip()
password = os.getenv("ADMIN_PASSWORD", "")
if not email or not password:
    raise SystemExit("Set ADMIN_EMAIL and ADMIN_PASSWORD in the environment before running this script")
if len(password) < 14:
    raise SystemExit("ADMIN_PASSWORD must be at least 14 characters")
with SessionLocal() as db:
    user = db.scalar(select(User).where(User.email == email))
    if user:
        user.name = name
        user.password_hash = password_hash.hash(password)
        user.role = "admin"
        print("Existing account promoted/reset as admin")
    else:
        db.add(User(email=email, name=name, password_hash=password_hash.hash(password), role="admin"))
        print("Admin account created")
    db.commit()
