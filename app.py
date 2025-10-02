import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

# -------------------------------------------------
# App Setup
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

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Clinic(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    slug = db.Column(db.String(80), unique=True, nullable=False)
    logo_url = db.Column(db.String(200))
    primary_color = db.Column(db.String(20), default="#1f6feb")


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey("admin.id"))
    action = db.Column(db.String(100), nullable=False)  # e.g., login, logout, clock_in, clock_out
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    details = db.Column(db.Text)
    admin = db.relationship("Admin", backref="audit_logs")


class Shift(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey("admin.id"))
    clock_in = db.Column(db.DateTime, default=datetime.utcnow)
    clock_out = db.Column(db.DateTime, nullable=True)

    admin = db.relationship("Admin", backref="shifts")

    @property
    def duration_hours(self):
        if self.clock_in and self.clock_out:
            return round((self.clock_out - self.clock_in).total_seconds() / 3600, 2)
        return None

# -------------------------------------------------
# Helpers
# -------------------------------------------------
def get_current_admin():
    admin_id = session.get("admin_id")
    if admin_id:
        return Admin.query.get(admin_id)
    return None

def log_action(admin_id, action, details=""):
    db.session.add(AuditLog(admin_id=admin_id, action=action, details=details))
    db.session.commit()

# -------------------------------------------------
# Routes
# -------------------------------------------------
@app.route("/")
def dashboard():
    admin = get_current_admin()
    return render_template("dashboard.html", admin=admin)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        admin = Admin.query.filter_by(username=username).first()
        if admin and admin.check_password(password):
            session["admin_id"] = admin.id
            flash("Login successful!", "success")
            log_action(admin.id, "login", f"{username} logged in.")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid username or password", "error")

    return render_template("login.html")

@app.route("/logout")
def logout():
    admin = get_current_admin()
    if admin:
        log_action(admin.id, "logout", f"{admin.username} logged out.")
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))

@app.route("/clock-in")
def clock_in():
    admin = get_current_admin()
    if not admin:
        flash("You must be logged in to clock in.", "error")
        return redirect(url_for("login"))

    active_shift = Shift.query.filter_by(admin_id=admin.id, clock_out=None).first()
    if active_shift:
        flash("You are already clocked in!", "error")
    else:
        shift = Shift(admin_id=admin.id)
        db.session.add(shift)
        log_action(admin.id, "clock_in", "Staff clocked in.")
        flash("Clock-in successful!", "success")
    return redirect(url_for("dashboard"))

@app.route("/clock-out")
def clock_out():
    admin = get_current_admin()
    if not admin:
        flash("You must be logged in to clock out.", "error")
        return redirect(url_for("login"))

    active_shift = Shift.query.filter_by(admin_id=admin.id, clock_out=None).first()
    if not active_shift:
        flash("You are not clocked in!", "error")
    else:
        active_shift.clock_out = datetime.utcnow()
        log_action(admin.id, "clock_out", "Staff clocked out.")
        db.session.commit()
        flash("Clock-out successful!", "success")
    return redirect(url_for("dashboard"))

@app.route("/reports")
def reports():
    admin = get_current_admin()
    if not admin or not admin.is_superadmin:
        flash("Permission denied.", "error")
        return redirect(url_for("dashboard"))

    shifts = Shift.query.order_by(Shift.clock_in.desc()).all()
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(50).all()
    return render_template("reports.html", admin=admin, shifts=shifts, logs=logs)

# -------------------------------------------------
# Run (local only)
# -------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
