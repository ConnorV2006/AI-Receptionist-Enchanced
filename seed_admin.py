import os
from app import app, db
from app.models import Admin
from werkzeug.security import generate_password_hash

def seed_admin(username="admin", password="admin123"):
    with app.app_context():   # ✅ ensures DB queries run inside Flask's context
        # Check if admin already exists
        existing = Admin.query.filter_by(username=username).first()
        if existing:
            print(f"⚠️ Admin '{username}' already exists. Skipping.")
            return

        # Create new admin with hashed password
        admin = Admin(username=username)
        admin.password_hash = generate_password_hash(password)
        db.session.add(admin)
        db.session.commit()

        print(f"✅ Admin user created: username={username}, password={password}")

if __name__ == "__main__":
    # Use env vars if available
    username = os.environ.get("ADMIN_USERNAME", "admin")
    password = os.environ.get("ADMIN_PASSWORD", "admin123")
    seed_admin(username, password)
