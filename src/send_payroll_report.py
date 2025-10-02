import os
import smtplib
from email.message import EmailMessage
from datetime import datetime
from app import app, db, Shift, Admin, create_payroll_workbook

def send_payroll_email():
    to_email = os.getenv("REPORT_TO_EMAIL")
    if not to_email:
        print("REPORT_TO_EMAIL not set; skipping email.")
        return

    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    smtp_from = os.getenv("SMTP_FROM", to_email)

    if not (smtp_host and smtp_user and smtp_pass):
        print("SMTP_* env vars not fully set; skipping email.")
        return

    # Prepare workbook
    with app.app_context():
        shifts = Shift.query.order_by(Shift.clock_in.desc()).all()
        buf = create_payroll_workbook(shifts)
        data = buf.getvalue()

    msg = EmailMessage()
    msg["Subject"] = f"Payroll Report - {datetime.utcnow().strftime('%Y-%m-%d')}"
    msg["From"] = smtp_from
    msg["To"] = to_email
    msg.set_content("Attached is the weekly payroll report (Excel).")

    msg.add_attachment(
        data,
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="shifts_with_payroll.xlsx"
    )

    with smtplib.SMTP(smtp_host, smtp_port) as s:
        s.starttls()
        s.login(smtp_user, smtp_pass)
        s.send_message(msg)

    print("✅ Payroll email sent to", to_email)

if __name__ == "__main__":
    with app.app_context():
        send_payroll_email()
