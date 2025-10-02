import os
from datetime import datetime, timedelta
from app import db, Clinic, Appointment, Patient, get_twilio_client, get_twilio_from_number, build_reminder_message

def send_appointment_reminders():
    now = datetime.utcnow()
    tomorrow = now + timedelta(days=1)

    # Range: midnight tomorrow → midnight next day
    start = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 0, 0, 0)
    end = start + timedelta(days=1)

    appointments = Appointment.query.filter(
        Appointment.appt_time >= start,
        Appointment.appt_time < end
    ).all()

    if not appointments:
        print("✅ No appointments scheduled for tomorrow. Nothing to send.")
        return

    client = get_twilio_client()

    for appt in appointments:
        clinic = appt.clinic
        patient = appt.patient
        from_number = get_twilio_from_number(clinic)

        # ✅ Human-friendly reminder message
        body = build_reminder_message(clinic, patient, appt)

        try:
            client.messages.create(
                body=body,
                from_=from_number,
                to=patient.phone_number
            )
            print(f"📤 Reminder sent to {patient.full_name} ({patient.phone_number})")
        except Exception as e:
            print(f"⚠️ Failed to send reminder to {patient.full_name}: {e}")

if __name__ == "__main__":
    send_appointment_reminders()
