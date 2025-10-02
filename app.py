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

# -------------------------------------------------
# Helpers
# -------------------------------------------------
def get_current_admin():
    admin_id = session.get("admin_id")
    if admin_id:
        return Admin.query.get(admin_id)
    return None

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
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid username or password", "error")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))

@app.route("/clinic/<slug>/dashboard")
def clinic_dashboard(slug):
    admin = get_current_admin()
    clinic = Clinic.query.filter_by(slug=slug).first()
    if not clinic:
        flash("Clinic not found.", "error")
        return redirect(url_for("dashboard"))
    return render_template("clinic_dashboard.html", clinic=clinic, admin=admin)

@app.route("/clinic/<slug>/manager", methods=["GET", "POST"])
def clinic_manager(slug):
    admin = get_current_admin()
    clinic = Clinic.query.filter_by(slug=slug).first()
    if not clinic:
        flash("Clinic not found.", "error")
        return redirect(url_for("dashboard"))

    if not admin or not admin.is_superadmin:
        flash("You do not have permission to access this page.", "error")
        return redirect(url_for("clinic_dashboard", slug=slug))

    if request.method == "POST":
        clinic.name = request.form.get("name", clinic.name)
        clinic.logo_url = request.form.get("logo_url", clinic.logo_url)
        clinic.primary_color = request.form.get("primary_color", clinic.primary_color)
        db.session.commit()
        flash("Clinic settings updated!", "success")
        return redirect(url_for("clinic_dashboard", slug=slug))

    return render_template("clinic_manager.html", clinic=clinic, admin=admin)

# -------------------------------------------------
# Run (local only)
# -------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
