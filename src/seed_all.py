import os
import sys
import secrets
from datetime import datetime, timedelta

# Ensure we can import from app.py
sys.path.append(os.path.dirname(__file__))

from app import app, db, Admin, Clinic, ApiKey, CallLog, SmsLog
from werkzeug.security import generate_password_hash


def seed_admin(username="admin", password="admin123", is_superadmin=True, clinic_id=None):
    existing = Admin.query.filter_by(username=username).first()
    if existing:
        print(f"⚡ Skipped admin seeding: '{username}' already exists (updated settings).")
        existing.password_hash = generate_password_hash(password)
        existing.is_superadmin = is_superadmin
        existing.clinic_id = clinic_id
        db.session.commit()
    else:
        admin = Admin(
            username=username,
            password_hash=generate_password_hash(password),
            is_superadmin=is_superadmin,
            clinic_id=clinic_id
        )
        db.session.add(admin)
        db.session.commit()
        print(f"✅ Created admin '{username}'")


def seed_clinic(slug="test-clinic", name="Test Clinic", twilio_number="+1234567890", twilio_sid="dummySID", twilio_token="dummyTOKEN"):
    existing = Clinic.query.filter_by(slug=slug).first()
    if existing:
        print(f"⚡ Skipped clinic seeding: '{slug}' already exists (updated settings).")
        existing.name = name
        existing.twilio_number = twilio_number
        existing.twilio_sid = twilio_sid
        existing.twilio_token = twilio_token
        db.session.commit()
    else:
        clinic = Clinic(
            slug=slug,
            name=name,
            twilio_number=twilio_number,
            twilio_sid=twilio_sid,
            twilio_token=twilio_token
        )
        db.session.add(clinic)
        db.session.commit()
        print(f"✅ Created clinic '{slug}'")


def seed_api_key(clinic_slug="test-clinic", description="Test API Key"):
    clinic = Clinic.query.filter_by(slug=clinic_slug).first()
    if not clinic:
        print(f"❌ Clinic '{clinic_slug}' not found. Cannot seed API key.")
        return

    existing = ApiKey.query.filter_by(clinic_id=clinic.id, description=description).first()
    if existing:
        print(f"⚡ Skipped API key seeding: Key '{description}' already exists for clinic '{clinic_slug}'.")
        return

    key_value = secrets.token_hex(16)
    api_key = ApiKey(
        clinic_id=clinic.id,
        key=key_value,
        description=description,
        active=True
    )
    db.session.add(api_key)
    db.session.commit()
    print(f"✅ Created API key for clinic '{clinic_slug}': {key_value}")


def seed_call_logs(clinic_slug="test-clinic", count=5):
    clinic = Clinic.query.filter_by(slug=clinic_slug).first()
    if not clinic:
        print(f"❌ Clinic '{clinic_slug}' not found. Cannot seed call logs.")
        return

    existing_count = CallLog.query.filter_by(clinic_id=clinic.id).count()
    if existing_count > 0:
        print(f"⚡ Skipped call logs: {existing_count} logs already exist for clinic '{clinic_slug}'.")
        return

    now = datetime.utcnow()
    for i in range(count):
        log = CallLog(
            clinic_id=clinic.id,
            from_number=f"+1555000{i}",
            to_number=clinic.twilio_number,
            duration=30 + i * 10,
            timestamp=now - timedelta(minutes=i * 15),
            status="completed"
        )
        db.session.add(log)

    db.session.commit()
    print(f"✅ Seeded {count} call logs for clinic '{clinic_slug}'")


def seed_sms_logs(clinic_slug="test-clinic", count=5):
    clinic = Clinic.query.filter_by(slug=clinic_slug).first()
    if not clinic:
        print(f"❌ Clinic '{clinic_slug}' not found. Cannot seed SMS logs.")
        return

    existing_count = SmsLog.query.filter_by(clinic_id=clinic.id).count()
    if existing_count > 0:
        print(f"⚡ Skipped SMS logs: {existing_count} logs already exist for clinic '{clinic_slug}'.")
        return

    now = datetime.utcnow()
    for i in range(count):
        log = SmsLog(
            clinic_id=clinic.id,
            from_number=f"+1444000{i}",
            to_number=clinic.twilio_number,
            message_body=f"Test message {i+1}",
            timestamp=now - timedelta(minutes=i * 20),
            status="delivered"
        )
        db.session.add(log)

    db.session.commit()
    print(f"✅ Seeded {count} SMS logs for clinic '{clinic_slug}'")


if __name__ == "__main__":
    auto_seed = os.getenv("AUTO_SEED", "false").lower() == "true"
    if not auto_seed:
        print("⚠️ AUTO_SEED is disabled. Skipping seeding.")
        sys.exit(0)

    with app.app_context():
        print("🚀 Starting database seeding...")

        seed_clinic(slug="test-clinic", name="Test Clinic")
        clinic = Clinic.query.filter_by(slug="test-clinic").first()
        seed_admin(username="admin", password="admin123", is_superadmin=True, clinic_id=clinic.id)
        seed_api_key(clinic_slug="test-clinic")
        seed_call_logs(clinic_slug="test-clinic")
        seed_sms_logs(clinic_slug="test-clinic")

        print("✅ Seeding complete.")
