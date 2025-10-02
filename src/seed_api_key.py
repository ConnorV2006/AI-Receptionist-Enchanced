import os
import sys
import secrets

# Ensure we can import from app.py
sys.path.append(os.path.dirname(__file__))

from app import app, db, ApiKey, Clinic

def seed_api_key(clinic_slug="test-clinic", description="Test API Key"):
    with app.app_context():
        clinic = Clinic.query.filter_by(slug=clinic_slug).first()
        if not clinic:
            print(f"❌ Clinic '{clinic_slug}' not found. Please seed a clinic first.")
            return

        # Generate random key
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

if __name__ == "__main__":
    seed_api_key()
