"""Simple script to seed a default administrator into the database.

This script should be run using the Flask shell or via ``flask shell < prepared_seed_admin.py``.
It checks for an existing admin with the provided username and only creates
one if it does not already exist.  Adjust the ``username``, ``password``
and other fields as necessary before running.
"""
from werkzeug.security import generate_password_hash

from app import db  # type: ignore
from app import Admin  # type: ignore


def seed_admin(username: str = "admin", password: str = "changeme", **extra_fields) -> None:
    """Create a default admin account if none exists.

    Args:
        username: Desired username for the admin.
        password: Plain text password to be hashed.
        **extra_fields: Additional fields to set on the Admin model (e.g. clinic_id, is_superadmin).
    """
    # Check if an admin with this username already exists
    existing = Admin.query.filter_by(username=username).first()
    if existing:
        print(f"Admin '{username}' already exists; skipping creation.")
        return
    # Create the admin
    admin = Admin(username=username, **extra_fields)
    # Set the password hash using Werkzeug
    admin.password_hash = generate_password_hash(password)
    db.session.add(admin)
    db.session.commit()
    print(f"Admin '{username}' created successfully.")


if __name__ == "__main__":
    # When executed directly, create a superadmin with no clinic
    seed_admin(username="admin", password="changeme", is_superadmin=True, clinic_id=None)