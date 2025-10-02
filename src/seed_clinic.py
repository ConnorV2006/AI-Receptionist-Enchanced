import os
import sys
from werkzeug.security import generate_password_hash

# Ensure we can import from app.py
sys.path.append(os.path.dirname(__file__))

from app import app, db, Clinic

def seed_clinic(slug="test-clinic", name="Test Clinic", twilio_number="+1234567890", twilio_sid="dummySID", twilio_token="dummyTOKEN"):
    with app.app_context():
        existing = Clinic.query.filter_by(slug=slug).first()
        if existing:
            existing.name = name
            existing.twilio_number = twilio_number
            existing.twilio_sid = twilio_sid
            existing.twilio_token = twilio_token
            db.session.commit()
            print(f"🔄 Updated clinic '{slug}'")
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

if __name__ == "__main__":
    seed_clinic()
