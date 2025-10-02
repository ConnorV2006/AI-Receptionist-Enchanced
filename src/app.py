import os
from datetime import datetime
from urllib.parse import urlencode

from flask import (
    Flask, request, redirect, url_for, render_template, flash, abort, session, jsonify
)
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from twilio.rest import Client

# Optional OpenAI for call summaries
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
try:
    import openai
    if OPENAI_API_KEY:
        openai.api_key = OPENAI_API_KEY
except Exception:
    openai = None

# -------------------------------------------------
# App Config
# -------------------------------------------------
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev_secret")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

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
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinic.id"))

class Clinic(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    address = db.Column(db.String(255))
    city = db.Column(db.String(100))
    state = db.Column(db.String(50))
    zip = db.Column(db.String(20))
    twilio_number = db.Column(db.String(20))
    twilio_sid = db.Column(db.String(120))
    twilio_token = db.Column(db.String(120))
    auto_focus_enabled = db.Column(db.Boolean, default=False)
    logo_url = db.Column(db.String(500))
    primary_color = db.Column(db.String(20), default="#1f6feb")

class QuickReplyTemplate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinic.id"), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    body = db.Column(db.Text, nullable=False)
    clinic = db.relationship("Clinic", backref=db.backref("quick_replies", lazy=True))

class SmsLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinic.id"), nullable=False)
    from_number = db.Column(db.String(20))
    to_number = db.Column(db.String(20))
    message_body = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50))

class CallLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinic.id"), nullable=False)
    from_number = db.Column(db.String(20))
    to_number = db.Column(db.String(20))
    duration = db.Column(db.Integer)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50))
    recording_url = db.Column(db.String(500))
    transcript = db.Column(db.Text)
    ai_summary = db.Column(db.Text)

class Patient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinic.id"), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    phone_number = db.Column(db.String(32), nullable=False)
    clinic = db.relationship("Clinic", backref=db.backref("patients", lazy=True))

class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinic.id"), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"), nullable=False)
    appt_time = db.Column(db.DateTime, nullable=False)
    notes = db.Column(db.String(255))
    prep_instructions = db.Column(db.String(255))
    clinic = db.relationship("Clinic", backref=db.backref("appointments", lazy=True))
    patient = db.relationship("Patient", backref=db.backref("appointments", lazy=True))

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey("admin.id"))
    action = db.Column(db.String(255), nullable=False)
    details = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    admin = db.relationship("Admin", backref=db.backref("audit_logs", lazy=True))

# -------------------------------------------------
# Helpers
# -------------------------------------------------
def get_current_admin():
    admin_id = session.get("admin_id")
    return Admin.query.get(admin_id) if admin_id else None

def require_superadmin():
    admin = get_current_admin()
    if not admin or not admin.is_superadmin:
        abort(403)
    return admin

def log_action(admin, action, details=""):
    if not admin:
        return
    try:
        entry = AuditLog(admin_id=admin.id, action=action, details=details)
        db.session.add(entry)
        db.session.commit()
    except Exception:
        db.session.rollback()

def get_twilio_client(clinic=None):
    sid = clinic.twilio_sid if clinic and clinic.twilio_sid else os.getenv("TWILIO_ACCOUNT_SID")
    token = clinic.twilio_token if clinic and clinic.twilio_token else os.getenv("TWILIO_AUTH_TOKEN")
    return Client(sid, token)

def get_twilio_from_number(clinic):
    return clinic.twilio_number or os.getenv("TWILIO_NUMBER")

# -------------------------------------------------
# Routes
# -------------------------------------------------
@app.route("/")
def dashboard():
    admin = get_current_admin()
    return render_template("dashboard.html", admin=admin)

@app.route("/clinics/<slug>/dashboard")
def clinic_dashboard(slug):
    clinic = Clinic.query.filter_by(slug=slug).first_or_404()
    admin = get_current_admin()
    sms_logs = SmsLog.query.filter_by(clinic_id=clinic.id).order_by(SmsLog.timestamp.desc()).limit(10).all()
    call_logs = CallLog.query.filter_by(clinic_id=clinic.id).order_by(CallLog.timestamp.desc()).limit(10).all()
    appointments = Appointment.query.filter_by(clinic_id=clinic.id).order_by(Appointment.appt_time.asc()).limit(5).all()
    replies = QuickReplyTemplate.query.filter_by(clinic_id=clinic.id).all()
    return render_template("clinic_dashboard.html",
                           clinic=clinic,
                           admin=admin,
                           sms_logs=sms_logs,
                           call_logs=call_logs,
                           appointments=appointments,
                           replies=replies)

@app.route("/clinics/<slug>/settings", methods=["GET", "POST"])
def clinic_settings(slug):
    clinic = Clinic.query.filter_by(slug=slug).first_or_404()
    admin = get_current_admin()
    if request.method == "POST":
        clinic.auto_focus_enabled = bool(request.form.get("auto_focus_enabled"))
        clinic.logo_url = request.form.get("logo_url") or clinic.logo_url
        clinic.primary_color = request.form.get("primary_color") or clinic.primary_color
        db.session.commit()
        log_action(admin, "update_settings", "clinic settings updated")
        flash("Settings updated.", "success")
        return redirect(url_for("clinic_settings", slug=slug))
    return render_template("clinic_settings.html", clinic=clinic, admin=admin)

@app.route("/clinics/<slug>/manage", methods=["GET", "POST"])
def clinic_manager(slug):
    clinic = Clinic.query.filter_by(slug=slug).first_or_404()
    admin = require_superadmin()
    if request.method == "POST":
        clinic.name = request.form.get("name")
        clinic.address = request.form.get("address")
        clinic.city = request.form.get("city")
        clinic.state = request.form.get("state")
        clinic.zip = request.form.get("zip")
        clinic.twilio_number = request.form.get("twilio_number")
        clinic.logo_url = request.form.get("logo_url")
        clinic.primary_color = request.form.get("primary_color") or clinic.primary_color
        db.session.commit()
        log_action(admin, "manage_clinic", "clinic info updated")
        flash("Clinic info updated.", "success")
        return redirect(url_for("clinic_manager", slug=slug))
    return render_template("clinic_manager.html", clinic=clinic, admin=admin)

# Error handling
@app.errorhandler(403)
def forbidden_error(error):
    admin = get_current_admin()
    return render_template("403.html", admin=admin), 403

# -------------------------------------------------
# Run
# -------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
