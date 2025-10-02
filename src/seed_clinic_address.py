import os
from app import db, Clinic

def seed_clinic(slug, name, address, city, state, zip_code, twilio_number=None):
    clinic = Clinic.query.filter_by(slug=slug).first()
    if clinic:
        print(f"🔄 Updating clinic '{slug}'...")
        clinic.name = name
        clinic.address = address
        clinic.city = city
        clinic.state = state
        clinic.zip = zip_code
        if twilio_number:
            clinic.twilio_number = twilio_number
    else:
        print(f"➕ Creating new clinic '{slug}'...")
        clinic = Clinic(
            slug=slug,
            name=name,
            address=address,
            city=city,
            state=state,
            zip=zip_code,
            twilio_number=twilio_number,
        )
        db.session.add(clinic)

    db.session.commit()
    print(f"✅ Clinic '{slug}' saved successfully.")

if __name__ == "__main__":
    # Example: Update or insert your first clinic here
    seed_clinic(
        slug="pittsburg-clinic",
        name="Main Street Clinic",
        address="123 Main St",
        city="Pittsburg",
        state="KS",
        zip_code="66762",
        twilio_number="+16205551234"  # optional, remove if not needed
    )
