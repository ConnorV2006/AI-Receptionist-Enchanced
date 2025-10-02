import os
import logging
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, Response
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from cryptography.fernet import Fernet
from twilio.twiml.voice_response import VoiceResponse

# -------------------------------------------------
# App + Config
# -------------------------------------------------
app = Flask(__name__)

app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY", "dev_secret")
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# -------------------------------------------------
# Encryption key
# -------------------------------------------------
APP_ENC_KEY = os.environ.get("APP_ENC_KEY")
if not APP_ENC_KEY:
    logging.warning("⚠️ APP_ENC_KEY not set. Generating temporary key.")
    APP_ENC_KEY = Fernet.generate_key().decode()
    logging.warning(f"⚠️ Save this key in Render env vars as APP_ENC_KEY: {APP_ENC_KEY}")
fernet = Fernet(APP_ENC_KEY.encode())

# -------------------------------------------------
# Models
# -------------------------------------------------
class Clinic(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False, default="Clinic")
    twilio_number = db.Column(db.String(20))
    twilio_sid = db.Column(db.String(100))
    twilio_token = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class CallLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey('clinic.id'), nullable=False)
    caller_number = db.Column(db.String(20))
    call_time = db.Column(db.DateTime, default=datetime.utcnow)
    transcript = db.Column(db.Text)
    sentiment = db.Column(db.String(50))

class MessageLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey('clinic.id'), nullable=False)
    from_number = db.Column(db.String(20))
    to_number = db.Column(db.String(20))
    body = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# -------------------------------------------------
# Routes
# -------------------------------------------------
@app.route('/')
def index():
    return render_template("dashboard.html")

@app.route('/<slug>/admin', methods=['GET', 'POST'])
def admin_dashboard(slug):
    clinic = Clinic.query.filter_by(slug=slug).first_or_404()
    if request.method == "POST":
        clinic.name = request.form.get("name") or clinic.name
        clinic.twilio_number = request.form.get("twilio_number")
        clinic.twilio_sid = request.form.get("twilio_sid")
        clinic.twilio_token = request.form.get("twilio_token")
        db.session.commit()
        flash("Clinic settings updated.", "success")
        return redirect(url_for("admin_dashboard", slug=slug))
    return render_template("clinic_dashboard.html", clinic=clinic)

@app.route("/twilio/voice/<slug>", methods=['POST'])
def handle_call(slug):
    clinic = Clinic.query.filter_by(slug=slug).first_or_404()
    caller = request.form.get("From")

    log = CallLog(
        clinic_id=clinic.id,
        caller_number=caller,
        transcript="",
        sentiment="pending"
    )
    db.session.add(log)
    db.session.commit()

    resp = VoiceResponse()
    resp.say("Hello, you’ve reached the AI Receptionist. Please leave your message after the tone.")
    resp.record(max_length=120, action="/twilio/recording", method="POST")
    return Response(str(resp), mimetype="text/xml")

@app.errorhandler(404)
def not_found(e):
    return render_template("base.html", message="Page not found"), 404

@app.errorhandler(500)
def server_error(e):
    return render_template("base.html", message="Internal server error"), 500

if __name__ == "__main__":
    app.run()
