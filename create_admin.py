"""
Bootstrap script for creating an initial admin account.

This script allows you to create a new administrator account from the
command line without having to interact with the web interface. It reads
credentials from environment variables or prompts for them interactively.
Run this script once after deploying the application to seed a super admin.

Usage (with environment variables):

    FLASK_APP=app.py DATABASE_URL=... python create_admin.py

Set the following environment variables:

    ADMIN_USERNAME – desired username for the new admin
    ADMIN_PASSWORD – desired password for the new admin
    ADMIN_EMAIL    – email address for the admin (optional)
    ADMIN_CLINIC_ID – (optional) clinic ID to bind the admin to. If omitted,
                      the admin will be a super admin.

Alternatively, run without environment variables and you will be prompted for
each value. After running, the admin will be persisted in the database.
"""
import os
import getpass

from app import app, db, Admin


def main() -> None:
    username = os.environ.get("ADMIN_USERNAME") or input("Admin username: ")
    password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass(
        "Admin password: "
    )
    email = os.environ.get("ADMIN_EMAIL") or input(
        "Admin email (optional, press enter to skip): "
    )
    clinic_id_env = os.environ.get("ADMIN_CLINIC_ID") or input(
        "Clinic ID (optional, leave blank for super admin): "
    )
    clinic_id = int(clinic_id_env) if clinic_id_env else None

    with app.app_context():
        if Admin.query.filter_by(username=username).first():
            print(f"An admin with username '{username}' already exists.")
            return
        admin = Admin(username=username, clinic_id=clinic_id, is_superadmin=clinic_id is None)
        admin.set_password(password)
        # store email in username or separate field? For now ignore; update model if needed
        db.session.add(admin)
        db.session.commit()
        print(
            f"Admin '{username}' created successfully. Super admin: {admin.is_superadmin}."
        )


if __name__ == "__main__":
    main()