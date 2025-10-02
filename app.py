import os
import secrets
import logging
from datetime import datetime, timedelta
from functools import wraps
from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, session, Response
)
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from cryptography.fernet import Fernet, InvalidToken
from twilio.rest import Client
import random

# -------------------------------------------------
# App Setup
# -------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(16))
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Session timeout config
SESSION_TIMEOUT = 30 * 60  # 30 minutes

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# -------------------------------------------------
# Models
# -------------------------------------------------
class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default="staff")  # superadmin, manager, staff
    phone_number = db.Column(db.String(20))  # for 2FA

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey("admin.id"))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    action = db.Column(db.String(255))
    details = db.Column(db.Text)
    admin = db.relationship("Admin")


# -------------------------------------------------
# Helpers
# -------------------------------------------------
def log_action(admin_id, action, details=""):
    log = AuditLog(admin_id=admin_id, action=action, details=details)
    db.session.add(log)
    db.session.commit()


def get_current_admin():
    if "admin_id" not in session:
        return None
    admin = Admin.query.get(session["admin_id"])
    return admin


def require_role(*roles):
    """Decorator to restrict route access to specific roles"""
    def wrapper(func):
        @wraps(func)
        def decorated(*args, **kwargs):
            admin = get_current_admin()
            if not admin or admin.role not in roles:
                flash("Permission denied.", "error")
                return redirect(url_for("dashboard"))
            return func(*args, **kwargs)
        return decorated
    return wrapper


@app.before_request
def check_session_timeout():
    if "last_active" in session:
        if datetime.utcnow() > session["last_active"] + timedelta(seconds=SESSION_TIMEOUT):
            session.clear()
            flash("Session expired. Please log in again.", "warning")
            return redirect(url_for("login"))
    session["last_active"] = datetime.utcnow()


# -------------------------------------------------
# Routes
# -------------------------------------------------
@app.route("/")
def dashboard():
    admin = get_current_admin()
    if not admin:
        return redirect(url_for("login"))
    return render_template("dashboard.html", admin=admin)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        admin = Admin.query.filter_by(username=username).first()
        if admin and admin.check_password(password):
            # Step 1: Generate 2FA code
            code = str(random.randint(100000, 999999))
            session["pending_2fa"] = {"id": admin.id, "code": code, "timestamp": datetime.utcnow().isoformat()}

            # Send via SMS (Twilio)
            try:
                client = Client(os.environ.get("TWILIO_SID"), os.environ.get("TWILIO_TOKEN"))
                if admin.phone_number:
                    client.messages.create(
                        body=f"Your verification code is: {code}",
                        from_=os.environ.get("TWILIO_NUMBER"),
                        to=admin.phone_number
                    )
            except Exception as e:
                print(f"⚠️ 2FA SMS failed: {e}")

            flash("2FA code sent to your phone. Enter below.", "info")
            return redirect(url_for("two_factor"))
        else:
            log_action(None, "failed_login", f"Username={username}")
            flash("Invalid credentials", "error")

    return render_template("login.html")


@app.route("/two-factor", methods=["GET", "POST"])
def two_factor():
    if "pending_2fa" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        code = request.form["code"]
        pending = session["pending_2fa"]
        if code == pending["code"]:
            admin = Admin.query.get(pending["id"])
            session.clear()
            session["admin_id"] = admin.id
            session["last_active"] = datetime.utcnow()
            log_action(admin.id, "login_success")
            flash("Login successful!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid code", "error")

    return render_template("two_factor.html")


@app.route("/logout")
def logout():
    admin = get_current_admin()
    if admin:
        log_action(admin.id, "logout")
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


@app.route("/admin/manage")
@require_role("superadmin")
def manage_admins():
    admins = Admin.query.all()
    return render_template("admins_list.html", admins=admins)


@app.route("/admin/promote/<int:admin_id>")
@require_role("superadmin")
def promote_admin(admin_id):
    target = Admin.query.get_or_404(admin_id)
    old_role = target.role
    target.role = "manager"
    db.session.commit()
    log_action(get_current_admin().id, "role_change", f"{target.username}: {old_role} -> manager")
    flash(f"{target.username} promoted to manager.", "success")
    return redirect(url_for("manage_admins"))


# -------------------------------------------------
# Error Handlers
# -------------------------------------------------
@app.errorhandler(403)
def forbidden(e):
    return render_template("403.html"), 403

@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(debug=True)
