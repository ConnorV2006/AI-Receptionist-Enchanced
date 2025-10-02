import os
import sys
from datetime import datetime, timedelta, date

sys.path.append(os.path.dirname(__file__))

from app import app, db, Clinic, Appointment, SmsLog
from twilio.rest import Client

def get_twilio_client():
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    if not sid or not token:
        raise RuntimeError("Missing TWILIO_ACCOUNT_SID or TWILIO_AUTH_TOKEN")
    return Client(sid, token)

def get_twilio_from_number(clinic):
    return (clinic.twilio_number or os.getenv("TWILIO_NUMBER"))

def send_reminders_for_clinic(clinic):
    client = get_twilio_client()
    from_number = get_twilio_from_number(clinic)
    if not from_number:
        print(f"[{clinic.slug}] No from number configured — skipping.")
        return

    # Define "tomorrow" window in UTC (adjust if you store local times)
    now = datetime.utcnow()
    start = (now + timedelta(days=1)).date()
    end = start + timedelta(days=1)

    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.min.time())

    appts = Appointment.query.filter(
        Appointment.clinic_id == clinic.id,
        Appointment.appt_time >= start_dt,
        Appointment.appt_time < end_dt
    ).all()

    print(f"[{clinic.slug}] Found {len(appts)} appointments for tomorrow.")

    for appt in appts:
        to_number = appt.patient.phone_number
        msg = f"Reminder: You have an appointment on {appt.appt_time.strftime('%Y-%m-%d %H:%M UTC')} at {clinic.name}."
        try:
            client.messages.create(body=msg, from_=from_number, to=to_number)
            sms_log = SmsLog(
                clinic_id=clinic.id,
                from_number=from_number,
                to_number=to_number,
                message_body=msg,
                timestamp=datetime.utcnow(),
                status="queued",
            )
            db.session.add(sms_log)
            print(f"[{clinic.slug}] Reminder sent to {to_number}")
        except Exception as e:
            print(f"[{clinic.slug}] Failed to send to {to_number}: {e}")

    db.session.commit()

if __name__ == "__main__":
    with app.app_context():
        clinics = Clinic.query.all()
        for c in clinics:
            send_reminders_for_clinic(c)
