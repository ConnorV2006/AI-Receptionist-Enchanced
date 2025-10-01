# Enhanced AI Receptionist

This project is a minimal yet functional AI receptionist backend built with
Flask, SQLAlchemy and Twilio. It builds upon the cleaned version of the
project you supplied and introduces several much‑requested features:

* **Per‑clinic API keys** – generate and revoke API keys unique to each
  clinic for use with external services or integrations.
* **Admin CRUD** – manage administrator accounts through a simple UI. Create,
  edit and delete admins and optionally grant super‑admin privileges.
* **Call logs** – record inbound and outbound phone calls with Twilio and
  browse recent history from within each clinic dashboard.
* **Login page** – secure the administrative interface with username and
  password authentication.

## Quick start

1. **Install dependencies**

   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure environment variables**

   Create a `.env` file or export the following variables in your shell:

   ```bash
   # Core configuration
   export FLASK_APP=app.py
   export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
   export DATABASE_URL="sqlite:///local.db"
   # Create at least one admin user on first run via Flask shell or CLI.

   # Encryption for Twilio credentials (32‑byte base64 key)
   export APP_ENC_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"

   # Optional: global Twilio credentials used when clinics don't specify their own
   export TWILIO_ACCOUNT_SID="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
   export TWILIO_AUTH_TOKEN="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
   export TWILIO_FROM_NUMBER="+15551234567"
   ```

3. **Initialize the database**

   ```bash
   flask db init
   flask db migrate -m "initial tables"
   flask db upgrade
   ```

4. **Create a clinic and admin**

   ```bash
   # Create clinic via CLI (reads env vars CLINIC_SLUG and CLINIC_NAME)
   export CLINIC_SLUG="demo"
   export CLINIC_NAME="Demo Clinic"
   flask create-clinic

   # Create an admin via Flask shell
   flask shell
   >>> from app import db, Admin
   >>> admin = Admin(username="admin", is_superadmin=True)
   >>> admin.set_password("changeme")
   >>> db.session.add(admin)
   >>> db.session.commit()
   ```

5. **Run the application**

   ```bash
   flask run
   ```

Visit `http://localhost:5000/login` and authenticate with your admin
credentials. Once logged in you can create additional clinics and admins, manage
API keys and view recent SMS and call logs.

## Deployment on Render

This repository includes a `Procfile`, `runtime.txt` and `render-build.sh`
script for easy deployment to Render.com. When creating a new web service set
`./render-build.sh` as the build command and ensure the following environment
variables are configured: `DATABASE_URL`, `SECRET_KEY`, `APP_ENC_KEY` and
`ADMIN_PASSWORD` (optional fallback for Twilio SMS replies). The build script
will automatically apply migrations on each deploy.

## Security considerations

* The API keys generated for clinics are stored in plaintext for simplicity. In
  a production system you should only store a hash of the key and reveal the
  plaintext only once at creation time.
* Administrator passwords are hashed using Werkzeug’s `generate_password_hash`.
  Always use strong, unique passwords and consider enforcing multi‑factor
  authentication for critical systems.
* Twilio credentials are encrypted at rest using a Fernet key loaded from
  `APP_ENC_KEY`. Rotate this key carefully; existing encrypted credentials
  become irrecoverable if you lose or change the key.
