import os
from datetime import datetime, timedelta
from email.message import EmailMessage
import smtplib

from app import db, Clinic, SmsLog, CallLog

def build_daily_report():
    now = datetime.utcnow()
    start = datetime(now.year, now.month, now.day, 0, 0, 0)
    end = start + timedelta(days=1)

    lines = []
    for clinic in Clinic.query.all():
        sms_count = SmsLog.query.filter(
            SmsLog.clinic_id == clinic.id,
            SmsLog.timestamp >= start,
            SmsLog.timestamp < end
        ).count()
        call_count = CallLog.query.filter(
            CallLog.clinic_id == clinic.id,
            CallLog.timestamp >= start,
            CallLog.timestamp < end
        ).count()
        lines.append(f"{clinic.name}: SMS={sms_count}, Calls={call_count}")
    return "Daily Communication Report\n\n" + "\n".join(lines)

def maybe_email_report(report_text):
    to_email = os.getenv("REPORT_TO_EMAIL")  # boss email
    if not to_email:
        print("No REPORT_TO_EMAIL set; printing report:\n")
        print(report_text)
        return

    sender = os.getenv("SMTP_FROM", to_email)
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    pwd = os.getenv("SMTP_PASS")

    if not host or not user or not pwd:
        print("SMTP not configured; printing report instead:\n")
        print(report_text)
        return

    msg = EmailMessage()
    msg["Subject"] = "Daily Clinic Communication Report"
    msg["From"] = sender
    msg["To"] = to_email
    msg.set_content(report_text)

    with smtplib.SMTP(host, port) as s:
        s.starttls()
        s.login(user, pwd)
        s.send_message(msg)
    print("✅ Daily report emailed.")

if __name__ == "__main__":
    report = build_daily_report()
    maybe_email_report(report)
