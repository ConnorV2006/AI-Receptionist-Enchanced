import os
from datetime import datetime
from flask import (
    Flask, request, redirect, url_for, render_template, flash
)
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from twilio.rest import Client

# -------------------------------------------------
# App Config
# -------------------------------------------------
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY", "dev_secret")
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# -------------------------------------------------
# Models
# -------------------------------------------------
class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_superadmin = db.Column(db.Boolean, default=False)
    clinic_id = db.Column(db.Integer, db.ForeignKey('clinic.id'), nullable=True)

class Clinic(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    twilio_number = db.Column(db.String(20))
    twilio_sid = db.Column(db.String(120))
    twilio_token = db.Column(db.String(120))

class ApiKey(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey('clinic.id'), nullable=False)
    key = db.Column(db.String(64), unique=True, nullable=False)
    description = db.Column(db.String(255))
    active = db.Column(db.Boolean, default=True)

class CallLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey('clinic.id'), nullable=False)
    from_number = db.Column(db.String(20))
    to_number = db.Column(db.String(20))
    duration = db.Column(db.Integer)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50))

class SmsLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey('clinic.id'), nullable=False)
    from_number = db.Column(db.String(20))
    to_number = db.Column(db.String(20))
    message_body = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50))

# ---- New Models ----
class Patient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey('clinic.id'), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    phone_number = db.Column(db.String(32), nullable=False)

    clinic = db.relationship('Clinic', backref=db.backref('patients', lazy=True))

class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey('clinic.id'), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'), nullable=False)
    appt_time = db.Column(db.DateTime, nullable=False)
    notes = db.Column(db.String(255))

    clinic = db.relationship('Clinic', backref=db.backref('appointments', lazy=True))
    patient = db.relationship('Patient', backref=db.backref('appointments', lazy=True))

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.id'), nullable=False)
    action = db.Column(db.String(255), nullable=False)
    details = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    admin = db.relationship('Admin', backref=db.backref('audit_logs', lazy=True))

class QuickReplyTemplate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey('clinic.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    body = db.Column(db.Text, nullable=False)

    clinic = db.relationship('Clinic', backref=db.backref('quick_replies', lazy=True))

# -------------------------------------------------
# Helpers
# -------------------------------------------------
def get_twilio_client():
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    return Client(sid, token)

def get_twilio_from_number(clinic):
    return clinic.twilio_number or os.getenv("TWILIO_NUMBER")

def log_action(admin, action, details=""):
    entry = AuditLog(
        admin_id=admin.id,
        action=action,
        details=details,
        timestamp=datetime.utcnow()
    )
    db.session.add(entry)
    db.session.commit()

# -------------------------------------------------
# Routes
# -------------------------------------------------
@app.route("/")
def dashboard():
    return render_template("dashboard.html")

@app.route("/clinics/<slug>/dashboard")
def clinic_dashboard(slug):
    clinic = Clinic.query.filter_by(slug=slug).first_or_404()
    sms_logs = SmsLog.query.filter_by(clinic_id=clinic.id).order_by(SmsLog.timestamp.desc()).limit(10).all()
    call_logs = CallLog.query.filter_by(clinic_id=clinic.id).order_by(CallLog.timestamp.desc()).limit(10).all()
    appointments = Appointment.query.filter_by(clinic_id=clinic.id).order_by(Appointment.appt_time.asc()).limit(5).all()
    replies = QuickReplyTemplate.query.filter_by(clinic_id=clinic.id).all()
    return render_template("clinic_dashboard.html", clinic=clinic, sms_logs=sms_logs, call_logs=call_logs, appointments=appointments, replies=replies)

@app.route("/clinics/<slug>/send-sms", methods=["POST"])
def send_sms(slug):
    clinic = Clinic.query.filter_by(slug=slug).first_or_404()
    to_number = request.form.get("to")
    body = request.form.get("message", "").strip()

    if not to_number or not body:
        flash("Phone number and message are required.", "error")
        return redirect(url_for("clinic_dashboard", slug=slug))

    client = get_twilio_client()
    from_number = get_twilio_from_number(clinic)

    client.messages.create(body=body, from_=from_number, to=to_number)

    sms_log = SmsLog(
        clinic_id=clinic.id,
        from_number=from_number,
        to_number=to_number,
        message_body=body,
        timestamp=datetime.utcnow(),
        status="queued",
    )
    db.session.add(sms_log)
    db.session.commit()

    # Example admin log (replace with session user in real app)
    # log_action(current_admin, "Sent SMS", f"To {to_number}, message: {body[:50]}")

    flash("SMS sent successfully.", "success")
    return redirect(url_for("clinic_dashboard", slug=slug))

@app.route("/clinics/<slug>/call", methods=["POST"])
def call_patient(slug):
    clinic = Clinic.query.filter_by(slug=slug).first_or_404()
    to_number = request.form.get("to")

    client = get_twilio_client()
    from_number = get_twilio_from_number(clinic)

    client.calls.create(
        twiml='<Response><Say>Hello, this is your clinic receptionist calling with a reminder.</Say></Response>',
        from_=from_number,
        to=to_number,
    )

    call_log = CallLog(
        clinic_id=clinic.id,
        from_number=from_number,
        to_number=to_number,
        duration=0,
        timestamp=datetime.utcnow(),
        status="queued",
    )
    db.session.add(call_log)
    db.session.commit()

    # Example admin log
    # log_action(current_admin, "Placed Call", f"To {to_number}")

    flash("Call initiated successfully.", "success")
    return redirect(url_for("clinic_dashboard", slug=slug))

@app.route("/admins/audit-logs")
def view_audit_logs():
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(100).all()
    return render_template("audit_logs.html", logs=logs)

@app.route("/clinics/<slug>/quick-replies", methods=["GET", "POST"])
def manage_quick_replies(slug):
    clinic = Clinic.query.filter_by(slug=slug).first_or_404()
    if request.method == "POST":
        title = request.form.get("title")
        body = request.form.get("body")
        if title and body:
            qr = QuickReplyTemplate(clinic_id=clinic.id, title=title, body=body)
            db.session.add(qr)
            db.session.commit()
            flash("Quick reply added.", "success")
        return redirect(url_for("manage_quick_replies", slug=slug))
    replies = QuickReplyTemplate.query.filter_by(clinic_id=clinic.id).all()
    return render_template("quick_replies.html", clinic=clinic, replies=replies)
