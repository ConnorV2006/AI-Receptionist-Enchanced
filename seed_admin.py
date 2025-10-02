import os
from app import app, db, Admin   # <-- import Admin directly from app.py
from werkzeug.security import generate_password_hash

def seed_admin(username="admin", password="admin123", is_superadmin=True, clinic_id=None):
    with app.app_context():   # ensures DB queries run inside Flask's context
        # Check if admin already exists
        existing = Admin.query.filter_by(username=username).first()
        if existing:
            print(f"⚠️ Admin '{username}' already exists. Skipping.")
            return

        # Create new admin with hashed password + extra fields
        admin = Admin(
            username=username,
            password_hash=generate_password_hash(password),
            is_superadmin=is_superadmin,
            clinic_id=clinic_id
        )

        db.session.add(admin)
        db.session.commit()

        print(f"✅ Admin user created: username={username}, password={password}, "
              f"is_superadmin={is_superadmin}, clinic_id={clinic_id}")

if __name__ == "__main__":
    # Pull values from environment variables if provided
    username = os.environ.get("ADMIN_USERNAME", "admin")
    password = os.environ.get("ADMIN_PASSWORD", "admin123")
    is_superadmin = os.environ.get("ADMIN_SUPERADMIN", "true").lower() == "true"
    clinic_id = os.environ.get("ADMIN_CLINIC_ID")

    seed_admin(username, password, is_superadmin, clinic_id)
