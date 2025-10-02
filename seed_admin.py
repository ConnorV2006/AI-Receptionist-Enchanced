import os
import sys
from werkzeug.security import generate_password_hash

# Ensure the current directory is in Python's path
sys.path.append(os.path.dirname(__file__))

from app import app, db, Admin   # app.py is in the same folder as this script

def seed_admin(username="admin", password="admin123", is_superadmin=True, clinic_id=None):
    with app.app_context():
        existing = Admin.query.filter_by(username=username).first()

        if existing:
            # Update existing admin
            existing.password_hash = generate_password_hash(password)
            existing.is_superadmin = is_superadmin
            existing.clinic_id = clinic_id
            db.session.commit()
            print(f"🔄 Updated existing admin '{username}' with new password and settings.")
        else:
            # Create a new admin
            admin = Admin(
                username=username,
                password_hash=generate_password_hash(password),
                is_superadmin=is_superadmin,
                clinic_id=clinic_id
            )
            db.session.add(admin)
            db.session.commit()
            print(f"✅ Created new admin: username={username}, password={password}, "
                  f"is_superadmin={is_superadmin}, clinic_id={clinic_id}")

if __name__ == "__main__":
    # Pull values from environment variables if provided
    username = os.environ.get("ADMIN_USERNAME", "admin")
    password = os.environ.get("ADMIN_PASSWORD", "admin123")
    is_superadmin = os.environ.get("ADMIN_SUPERADMIN", "true").lower() == "true"
    clinic_id = os.environ.get("ADMIN_CLINIC_ID")

    seed_admin(username, password, is_superadmin, clinic_id)
