import os
from app import db
from app.models import Admin
from werkzeug.security import generate_password_hash

def seed_admin():
    username = os.environ.get("ADMIN_USERNAME", "admin")
    password = os.environ.get("ADMIN_PASSWORD", "admin123")

    # Delete existing admins if you want only one
    Admin.query.delete()
    db.session.commit()

    # Create new admin with hashed password
    admin = Admin(username=username)
    admin.password_hash = generate_password_hash(password)

    db.session.add(admin)
    db.session.commit()

    print(f"✅ Admin user created: username={username}, password={password}")

if __name__ == "__main__":
    with db.session.begin():
        seed_admin()
