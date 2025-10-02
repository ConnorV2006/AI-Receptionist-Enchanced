import os
from app import app, db, Clinic, QuickReplyTemplate

# Default quick replies for all clinics
DEFAULT_REPLIES = [
    {"title": "Appt Reminder", "body": "Hello, this is a reminder from your clinic about your appointment tomorrow. Please reply YES to confirm."},
    {"title": "Confirm Appt", "body": "Your appointment has been confirmed. We look forward to seeing you!"},
    {"title": "Reschedule", "body": "We noticed you missed your appointment today. Would you like to reschedule? Reply with a preferred time."},
    {"title": "Running Late", "body": "Our provider is running a little behind today. Thank you for your patience."},
    {"title": "Clinic Closed", "body": "Our clinic is currently closed. Please call again during business hours. Thank you."},
    {"title": "Balance Due", "body": "Your balance is due. Please make a payment at your next visit or call us for options."},
]

def seed_quick_replies():
    with app.app_context():
        clinics = Clinic.query.all()
        for clinic in clinics:
            for reply in DEFAULT_REPLIES:
                # Check if this reply already exists for the clinic
                existing = QuickReplyTemplate.query.filter_by(
                    clinic_id=clinic.id, title=reply["title"]
                ).first()
                if not existing:
                    qr = QuickReplyTemplate(
                        clinic_id=clinic.id, title=reply["title"], body=reply["body"]
                    )
                    db.session.add(qr)
        db.session.commit()
        print("✅ Default quick replies seeded for all clinics.")

if __name__ == "__main__":
    seed_quick_replies()
