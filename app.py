import os
from datetime import datetime
from flask import (
    Flask, render_template, request, redirect, url_for, session, flash, abort
)
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash

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

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Clinic(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    location = db.Column(db.String(120))
    phone = db.Column(db.String(20))


# -------------------------------------------------
# Helpers
# -------------------------------------------------
def current_admin():
    if "admin_id" not in session:
        return None
    return Admin.query.get(session["admin_id"])


# -------------------------------------------------
# Routes
# -------------------------------------------------
@app.route("/")
def dashboard():
    admin = current_admin()
    if not admin:
        return redirect(url_for("login"))

    # Placeholder analytics
    analytics = {
        "calls_today": 15,
        "sms_today": 42,
        "clinics_count": Clinic.query.count(),
    }

    return render_template("dashboard.html", admin=admin, analytics=analytics)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        admin = Admin.query.filter_by(username=username).first()
        if admin and admin.check_password(password):
            session["admin_id"] = admin.id
            flash("Login successful ✅", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid credentials ❌", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully 👋", "info")
    return redirect(url_for("login"))


@app.route("/admins")
def admins_list():
    admin = current_admin()
    if not admin or not admin.is_superadmin:
        abort(403)
    admins = Admin.query.all()
    return render_template("admins_list.html", admins=admins)


# -------------------------------------------------
# Error Handlers
# -------------------------------------------------
@app.errorhandler(403)
def forbidden(e):
    return render_template("403.html"), 403

@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(500)
def server_error(e):
    return render_template("500.html"), 500


# -------------------------------------------------
# Run
# -------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
