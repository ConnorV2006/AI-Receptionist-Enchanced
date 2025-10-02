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
    import openai  # openai>=0.28 supported
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

    # Address for reminders + maps
    address = db.Column(db.String(255))
    city = db.Column(db.String(100))
    state = db.Column(db.String(50))
    zip = db.Column(db.String(20))

    # Twilio + UX prefs
    twilio_number = db.Column(db.String(20))
    twilio_sid = db.Column(db.String(120))
    twilio_token = db.Column(db.String(120))
    auto_focus_enabled = db.Column(db.Boolean, default=False)

    # White-label
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

    # AI summary fields
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
    prep_instructions = db.Column(db.String(255))  # optional extra UX
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
def get_twilio_client(clinic=None):
    sid = (clinic.twilio_sid if clinic and clinic.twilio_sid else os.getenv("TWILIO_ACCOUNT_SID"))
    token = (clinic.twilio_token if clinic and clinic.twilio_token else os.getenv("TWILIO_AUTH_TOKEN"))
    return Client(sid, token)

def get_twilio_from_number(clinic):
    return clinic.twilio_number or os.getenv("TWILIO_NUMBER")

def get_current_admin():
    """Placeholder; hook to your login later."""
    admin_id = session.get("admin_id")
    return Admin.query.get(admin_id) if admin_id else None

def require_superadmin():
    admin = get_current_admin()
    if not admin or not admin.is_superadmin:
        abort(403)
    return admin

def log_action(admin, action, details=""):
    try:
        entry = AuditLog(admin_id=admin.id if admin else None, action=action, details=details)
        db.session.add(entry)
        db.session.commit()
    except Exception:
        db.session.rollback()

def google_maps_link(clinic):
    address = ", ".join([c for c in [clinic.address, clinic.city, clinic.state, clinic.zip] if c])
    if not address:
        return ""
    q = urlencode({"api": 1, "query": address})
    return f"https://www.google.com/maps/search/?{q}"

def build_reminder_message(clinic, patient, appt):
    addr = ", ".join([c for c in [clinic.address, clinic.city, clinic.state, clinic.zip] if c]) or "your clinic location"
    maps = google_maps_link(clinic)
    time_str = appt.appt_time.strftime("%I:%M %p")
    prep = f" Prep: {appt.prep_instructions}" if appt.prep_instructions else ""
    tail = f" Map: {maps}" if maps else ""
    return (
        f"Hello {patient.full_name}, this is a friendly reminder from {clinic.name}. "
        f"Your appointment is scheduled for tomorrow at {time_str} at {addr}.{prep}{tail} "
        f"If you need to reschedule, please reply or call us. Thank you!"
    )

def ai_summarize_call(transcript_text):
    """Return a short summary. Uses OpenAI if available; otherwise fallback."""
    text = (transcript_text or "").strip()
    if not text:
        return None
    if openai and OPENAI_API_KEY:
        try:
            # Compatible with openai>=0.28 Completions API
            resp = openai.Completion.create(
                model="gpt-3.5-turbo-instruct",
                prompt=f"Summarize this phone call in one sentence, focusing on intent and next steps:\n\n{text}\n\nSummary:",
                max_tokens=64,
                temperature=0.2,
            )
            return resp.choices[0].text.strip()
        except Exception:
            pass
    # Fallback basic heuristic
    return (text[:160] + "...") if len(text) > 160 else text

# -------------------------------------------------
# Routes
# -------------------------------------------------
@app.route("/")
def dashboard():
    return render_template("dashboard.html")

# Clinic Dashboard
@app.route("/clinics/<slug>/dashboard")
def clinic_dashboard(slug):
    clinic = Clinic.query.filter_by(slug=slug).first_or_404()
    sms_logs = (SmsLog.query.filter_by(clinic_id=clinic.id)
                .order_by(SmsLog.timestamp.desc()).limit(10).all())
    call_logs = (CallLog.query.filter_by(clinic_id=clinic.id)
                 .order_by(CallLog.timestamp.desc()).limit(10).all())
    appointments = (Appointment.query.filter_by(clinic_id=clinic.id)
                    .order_by(Appointment.appt_time.asc()).limit(5).all())
    replies = QuickReplyTemplate.query.filter_by(clinic_id=clinic.id).all()
    return render_template("clinic_dashboard.html",
                           clinic=clinic,
                           sms_logs=sms_logs,
                           call_logs=call_logs,
                           appointments=appointments,
                           replies=replies)

# Send SMS
@app.route("/clinics/<slug>/send-sms", methods=["POST"])
def send_sms(slug):
    clinic = Clinic.query.filter_by(slug=slug).first_or_404()
    to_number = request.form.get("to")
    body = request.form.get("message", "").strip()
    if not to_number or not body:
        flash("Phone number and message are required.", "error")
        return redirect(url_for("clinic_dashboard", slug=slug))

    client = get_twilio_client(clinic)
    from_number = get_twilio_from_number(clinic)
    client.messages.create(body=body, from_=from_number, to=to_number)

    db.session.add(SmsLog(
        clinic_id=clinic.id,
        from_number=from_number,
        to_number=to_number,
        message_body=body,
        status="queued"
    ))
    db.session.commit()

    log_action(get_current_admin(), "send_sms", f"to={to_number} body={body[:120]}")
    flash("SMS sent successfully.", "success")
    return redirect(url_for("clinic_dashboard", slug=slug))

# Place Call (simple outbound demo)
@app.route("/clinics/<slug>/call", methods=["POST"])
def call_patient(slug):
    clinic = Clinic.query.filter_by(slug=slug).first_or_404()
    to_number = request.form.get("to")

    client = get_twilio_client(clinic)
    from_number = get_twilio_from_number(clinic)
    # Basic Say; real apps use a TwiML webhook for dynamic flows
    client.calls.create(
        twiml='<Response><Say>Hello, this is your clinic receptionist calling with a reminder.</Say></Response>',
        from_=from_number,
        to=to_number,
    )
    db.session.add(CallLog(
        clinic_id=clinic.id,
        from_number=from_number,
        to_number=to_number,
        duration=0,
        status="queued"
    ))
    db.session.commit()
    log_action(get_current_admin(), "place_call", f"to={to_number}")
    flash("Call initiated successfully.", "success")
    return redirect(url_for("clinic_dashboard", slug=slug))

# Settings (auto-focus toggle, white-label)
@app.route("/clinics/<slug>/settings", methods=["GET", "POST"])
def clinic_settings(slug):
    clinic = Clinic.query.filter_by(slug=slug).first_or_404()
    admin = get_current_admin()
    if request.method == "POST":
        # anyone with access can flip UX settings; lock down if you prefer
        clinic.auto_focus_enabled = bool(request.form.get("auto_focus_enabled"))
        clinic.logo_url = request.form.get("logo_url") or clinic.logo_url
        clinic.primary_color = request.form.get("primary_color") or clinic.primary_color
        db.session.commit()
        log_action(admin, "update_settings", f"auto_focus={clinic.auto_focus_enabled}, branding updated")
        flash("Settings updated.", "success")
        return redirect(url_for("clinic_settings", slug=slug))
    return render_template("clinic_settings.html", clinic=clinic)

# Boss-only Clinic Manager (edit clinic info)
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
        log_action(admin, "manage_clinic", "updated clinic profile")
        flash("Clinic information updated successfully.", "success")
        return redirect(url_for("clinic_manager", slug=slug))
    return render_template("clinic_manager.html", clinic=clinic)

# Patient Intake (public link: create a patient + optional appoint.)
@app.route("/clinics/<slug>/intake", methods=["GET", "POST"])
def patient_intake(slug):
    clinic = Clinic.query.filter_by(slug=slug).first_or_404()
    if request.method == "POST":
        full_name = request.form.get("full_name")
        phone = request.form.get("phone_number")
        if not full_name or not phone:
            flash("Name and phone are required.", "error")
            return redirect(url_for("patient_intake", slug=slug))
        p = Patient(clinic_id=clinic.id, full_name=full_name, phone_number=phone)
        db.session.add(p)
        db.session.commit()
        # Optional: create placeholder appt if provided
        appt_date = request.form.get("appt_time")
        if appt_date:
            try:
                dt = datetime.fromisoformat(appt_date)
                ap = Appointment(clinic_id=clinic.id, patient_id=p.id, appt_time=dt)
                db.session.add(ap)
                db.session.commit()
            except Exception:
                db.session.rollback()
        log_action(get_current_admin(), "patient_intake", f"new patient {full_name}")
        flash("Thank you. Your information has been received.", "success")
        return redirect(url_for("patient_intake", slug=slug))
    return render_template("intake_form.html", clinic=clinic)

# Communication Heatmap (by hour)
@app.route("/clinics/<slug>/reports/heatmap")
def comms_heatmap(slug):
    clinic = Clinic.query.filter_by(slug=slug).first_or_404()
    # Aggregate SMS + Calls by hour (0..23) UTC
    buckets = {h: {"sms": 0, "calls": 0} for h in range(24)}
    for s in SmsLog.query.filter_by(clinic_id=clinic.id).all():
        buckets[s.timestamp.hour]["sms"] += 1
    for c in CallLog.query.filter_by(clinic_id=clinic.id).all():
        buckets[c.timestamp.hour]["calls"] += 1
    # Provide total + rows
    rows = [{"hour": h, "sms": buckets[h]["sms"], "calls": buckets[h]["calls"]} for h in range(24)]
    total_sms = sum(r["sms"] for r in rows)
    total_calls = sum(r["calls"] for r in rows)
    return render_template("heatmap.html", clinic=clinic, rows=rows, total_sms=total_sms, total_calls=total_calls)

# Twilio webhook stubs for future: record + summarize calls
@app.route("/twilio/voice/recording", methods=["POST"])
def twilio_voice_recording():
    """Twilio posts RecordingUrl and CallSid after a call with <Record>. Save + summarize."""
    call_sid = request.form.get("CallSid")
    recording_url = request.form.get("RecordingUrl")
    # Find call by SID if you store it; otherwise, attach best effort
    log = CallLog.query.order_by(CallLog.timestamp.desc()).first()
    if log:
        log.recording_url = recording_url
        # In a real app, you'd fetch transcript via STT, then:
        # log.transcript = "...result from STT..."
        if openai and OPENAI_API_KEY and log.transcript:
            log.ai_summary = ai_summarize_call(log.transcript)
        db.session.commit()
    return ("", 204)

# Error page
@app.errorhandler(403)
def forbidden_error(error):
    return render_template("403.html"), 403

# Run
if __name__ == "__main__":
    app.run(debug=True)

