import os
import secrets
from datetime import datetime

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
    Response,
)
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
import sqlalchemy as sa
from cryptography.fernet import Fernet, InvalidToken

# Optional Twilio imports. These are only used when Twilio credentials are
# available and valid. The application gracefully degrades if the library or
# credentials are missing.
try:
    from twilio.rest import Client
    from twilio.twiml.messaging_response import MessagingResponse
    from twilio.twiml.voice_response import VoiceResponse
except Exception:
    Client = None  # type: ignore
    MessagingResponse = None  # type: ignore
    VoiceResponse = None  # type: ignore

# Attempt to import the OpenAI client. This optional dependency is used to
# generate concise summaries of incoming messages. If the package is not
# available or an API key is not configured, message summaries fall back
# to the original text (truncated). See ``generate_summary`` for details.
try:
    import openai  # type: ignore
except Exception:
    # If import fails, assign None. The application will gracefully fall back
    # to returning the original message when summarisation is unavailable.
    openai = None  # type: ignore

def generate_summary(text: str, max_tokens: int = 150) -> str:
    """Return a concise summary of the provided text.

    This helper attempts to call the OpenAI ChatCompletion API to produce
    a short summary of the caller's message. If the ``openai`` module
    isn't installed or the ``OPENAI_API_KEY`` environment variable is
    missing, the function returns a truncated version of the input text.

    Args:
        text: The raw input text from the caller or patient.
        max_tokens: Desired maximum number of tokens in the summary when
            using the OpenAI API. Defaults to 150 which roughly equates to
            50–75 words.

    Returns:
        A string containing either the AI‑generated summary or a truncated
        version of the original text.
    """
    # If OpenAI isn't available or no API key is configured, fall back
    # to returning at most the first 300 characters of the input.
    if openai is None or not os.environ.get("OPENAI_API_KEY"):
        return text[:300]
    try:
        # Build a prompt instructing the assistant to summarise concisely.
        system_prompt = (
            "You are a helpful medical receptionist. "
            "Summarise the following patient message in one or two sentences."
        )
        # Call the chat completion endpoint. We set a low temperature for
        # determinism and limit the number of tokens.
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",  # Use GPT‑3.5 for cost efficiency
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            max_tokens=max_tokens,
            temperature=0.3,
        )
        summary = response.choices[0].message["content"].strip()
        return summary
    except Exception as exc:
        # On any exception (network issues, API errors), log and fall back
        app.logger.warning("OpenAI summary generation failed: %s", exc)
        return text[:300]


###############################################################################
# Application setup
#
# The core Flask application is configured via environment variables. See
# README.md for details on each variable. SQLAlchemy is used for the ORM and
# Flask‑Migrate handles database migrations. A simple session‑based
# authentication mechanism protects admin routes.
###############################################################################

app = Flask(__name__)

# Database configuration. Render.com uses DATABASE_URL automatically. Locally
# this defaults to a SQLite file. Adjust as needed for other environments.
#
# SQLAlchemy 2.0 removed support for the legacy ``postgres://`` URI scheme and
# requires ``postgresql://`` instead. To support existing environment
# variables, coerce any postgres:// URI to the correct postgresql:// form. See
# https://docs.sqlalchemy.org/en/20/core/engines.html#postgresql for details.
database_url = os.environ.get("DATABASE_URL", "sqlite:///local.db")
if database_url.startswith("postgres://"):
    # Replace only the scheme prefix (first occurrence) to preserve the rest of
    # the connection string intact. This fixes ``Can't load plugin:
    # sqlalchemy.dialects:postgres`` errors when deploying to Render.
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# ---------------------------------------------------------------------------
# Session cookie security
#
# Protect session cookies by enabling secure settings. By default cookies are
# marked as HttpOnly and SameSite=Lax to mitigate cross‑site request forgery.
# The SESSION_COOKIE_SECURE flag is determined by an environment variable.
# When running locally over http (e.g. during development) you may set
# SESSION_COOKIE_SECURE to false. In production the default is true so that
# session cookies are only sent over https connections.
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SESSION_COOKIE_SECURE", "true").lower() == "true"

# Flask secret key for session handling. MUST be set for production use.
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

db = SQLAlchemy(app)
migrate = Migrate(app, db)


###############################################################################
# Encryption helper
#
# Clinic credentials (Twilio account SID and auth token) are stored encrypted in
# the database. A Fernet key stored in the APP_ENC_KEY environment variable is
# used to encrypt and decrypt these values. If the key is missing the
# application still runs but cannot decrypt credentials, and Twilio features
# degrade gracefully.
###############################################################################


def get_fernet() -> Fernet | None:
    """Return a Fernet instance based on the APP_ENC_KEY environment variable.

    If APP_ENC_KEY is not set or invalid, returns None. The Fernet key must be
    a 32‑byte urlsafe base64‑encoded string.
    """
    key = os.environ.get("APP_ENC_KEY")
    if not key:
        # Missing encryption key. Credentials cannot be decrypted.
        return None
    try:
        return Fernet(key)
    except Exception:
        # Invalid key format. Rather than crashing the app, warn the user
        # through logging and return None so encryption features silently fail.
        app.logger.warning("Invalid APP_ENC_KEY; cannot decrypt credentials.")
        return None


###############################################################################
# Models
###############################################################################


class Clinic(db.Model):
    """Represents a clinic configuration.

    Clinics are identified by a slug (e.g. "demo") which prefixes all Twilio
    webhook URLs. Each clinic can optionally store encrypted Twilio
    credentials (account SID and auth token) and a default sender number. A
    one‑to‑many relationship to API keys, admins, SMS logs and call logs is
    defined via backrefs.
    """

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)

    # Encrypted Twilio credentials. These values may be None when Twilio
    # integration is optional. Use ``decrypt_twilio_credentials`` to obtain
    # plaintext values when a valid APP_ENC_KEY is configured.
    twilio_account_sid_encrypted = db.Column(db.LargeBinary, nullable=True)
    twilio_auth_token_encrypted = db.Column(db.LargeBinary, nullable=True)
    twilio_from_number = db.Column(db.String(20), nullable=True)

    created_at = db.Column(db.DateTime, server_default=sa.func.now())

    def decrypt_twilio_credentials(self) -> tuple[str | None, str | None]:
        """Return decrypted Twilio account SID and auth token.

        If APP_ENC_KEY is not configured or decryption fails, returns (None,
        None). This method allows the rest of the application to transparently
        handle missing or invalid encryption keys without throwing exceptions.
        """
        f = get_fernet()
        if not f:
            return None, None
        try:
            account_sid = None
            auth_token = None
            if self.twilio_account_sid_encrypted:
                account_sid = f.decrypt(self.twilio_account_sid_encrypted).decode()
            if self.twilio_auth_token_encrypted:
                auth_token = f.decrypt(self.twilio_auth_token_encrypted).decode()
            return account_sid, auth_token
        except InvalidToken:
            app.logger.warning(
                "Failed to decrypt Twilio credentials for clinic %s. "
                "Ensure the APP_ENC_KEY is correct.",
                self.slug,
            )
            return None, None


class ApiKey(db.Model):
    """Stores per‑clinic API keys used for external integrations.

    Each key is associated with a clinic via a foreign key. A descriptive name
    helps identify the key (e.g. "Slack integration"). Keys are generated using
    Python's ``secrets.token_urlsafe`` ensuring sufficient entropy. Only the
    hash of the key should be stored if you intend to enforce key secrecy; for
    simplicity the raw key is stored here. Be cautious when exposing API keys
    through templates.
    """

    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinic.id"), nullable=False)
    key = db.Column(db.String(128), unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, server_default=sa.func.now())
    is_active = db.Column(db.Boolean, default=True)

    clinic = db.relationship("Clinic", backref=db.backref("api_keys", lazy=True))


class Admin(db.Model):
    """Represents an administrator account.

    Admins authenticate via username/password and can manage clinics,
    administrators, API keys and view logs. An admin may be associated with a
    specific clinic or may be a super‑admin. Super admins (``is_superadmin``)
    have access to all clinics.
    """

    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinic.id"), nullable=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_superadmin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, server_default=sa.func.now())

    clinic = db.relationship("Clinic", backref=db.backref("admins", lazy=True))

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class SmsLog(db.Model):
    """Logs inbound and outbound SMS messages.

    The body of the message and metadata such as direction, status, cost and
    currency are recorded. This model existed in previous iterations and is
    largely unchanged here.
    """

    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinic.id"), nullable=False)
    from_number = db.Column(db.String(20), nullable=False)
    to_number = db.Column(db.String(20), nullable=False)
    direction = db.Column(db.String(10), nullable=False)
    body = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(50), nullable=True)
    cost = db.Column(db.Numeric, nullable=True)
    currency = db.Column(db.String(3), nullable=True)
    created_at = db.Column(db.DateTime, server_default=sa.func.now())

    clinic = db.relationship("Clinic", backref=db.backref("sms_logs", lazy=True))


class CallLog(db.Model):
    """Logs inbound and outbound voice calls.

    Captures the Twilio call SID along with caller/callee information,
    direction, status and timestamps. Duration and notes fields allow
    post‑processing information such as call length or call summary to be
    persisted.
    """

    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinic.id"), nullable=False)
    call_sid = db.Column(db.String(64), nullable=True)
    from_number = db.Column(db.String(20), nullable=False)
    to_number = db.Column(db.String(20), nullable=False)
    direction = db.Column(db.String(10), nullable=False)
    status = db.Column(db.String(50), nullable=True)
    start_time = db.Column(db.DateTime, nullable=True)
    end_time = db.Column(db.DateTime, nullable=True)
    duration = db.Column(db.Integer, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, server_default=sa.func.now())

    clinic = db.relationship("Clinic", backref=db.backref("call_logs", lazy=True))


###############################################################################
# Session management and helpers
###############################################################################


def login_required(view_func):
    """Decorator to enforce that the current session has an authenticated admin.

    If not logged in, redirects to the login page with a next parameter to
    preserve the originally requested URL.
    """
    from functools import wraps

    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("admin_id"):
            return redirect(url_for("login", next=request.path))
        return view_func(*args, **kwargs)

    return wrapped


def current_admin() -> Admin | None:
    """Return the currently logged‑in Admin object, if any."""
    admin_id = session.get("admin_id")
    if admin_id is None:
        return None
    return Admin.query.get(admin_id)


def get_twilio_client(clinic: Clinic) -> Client | None:
    """Return a Twilio Client using clinic‑specific credentials.

    If clinic credentials cannot be decrypted or Twilio library is unavailable,
    returns None. This helper centralizes fallback behaviour.
    """
    account_sid, auth_token = clinic.decrypt_twilio_credentials()
    if not account_sid or not auth_token:
        return None
    if Client is None:
        return None
    try:
        return Client(account_sid, auth_token)
    except Exception as exc:
        app.logger.warning("Could not instantiate Twilio client: %s", exc)
        return None


###############################################################################
# Routes: Authentication
###############################################################################


@app.route("/login", methods=["GET", "POST"])
def login() -> str:
    """Render the login page and handle authentication POSTs."""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if not username or not password:
            flash("Please enter your username and password.")
            return render_template("login.html")
        admin = Admin.query.filter_by(username=username).first()
        if admin and admin.check_password(password):
            session["admin_id"] = admin.id
            next_url = request.args.get("next")
            return redirect(next_url or url_for("dashboard"))
        flash("Invalid username or password.")
    return render_template("login.html")


@app.route("/logout")
def logout() -> Response:
    """Log out the current admin by clearing the session."""
    session.pop("admin_id", None)
    return redirect(url_for("login"))


###############################################################################
# Routes: Core dashboards
###############################################################################


@app.route("/")
@login_required
def dashboard() -> str:
    """Simple dashboard listing clinics and links to manage them.

    Super admins see all clinics; clinic‑bound admins see only their clinic.
    """
    admin = current_admin()
    if not admin:
        abort(403)
    if admin.is_superadmin:
        clinics = Clinic.query.order_by(Clinic.created_at.desc()).all()
    elif admin.clinic_id:
        clinics = [Clinic.query.get(admin.clinic_id)] if admin.clinic_id else []
    else:
        clinics = []
    return render_template("dashboard.html", admin=admin, clinics=clinics)


@app.route("/clinics/<slug>/dashboard")
@login_required
def clinic_dashboard(slug: str) -> str:
    """Dashboard for a specific clinic showing logs and API keys."""
    clinic = Clinic.query.filter_by(slug=slug).first_or_404()
    admin = current_admin()
    if not admin:
        abort(403)
    # Non super admins may only view their own clinic
    if not admin.is_superadmin and admin.clinic_id != clinic.id:
        abort(403)
    sms_logs = SmsLog.query.filter_by(clinic_id=clinic.id).order_by(
        SmsLog.created_at.desc()
    ).limit(50)
    call_logs = CallLog.query.filter_by(clinic_id=clinic.id).order_by(
        CallLog.created_at.desc()
    ).limit(50)
    return render_template(
        "clinic_dashboard.html",
        clinic=clinic,
        sms_logs=sms_logs,
        call_logs=call_logs,
    )


###############################################################################
# Routes: Admin CRUD
###############################################################################


@app.route("/admins")
@login_required
def admins_list() -> str:
    """List administrator accounts.

    Super admins may view all admin accounts; non‑super admins are forbidden.
    """
    admin = current_admin()
    if not admin or not admin.is_superadmin:
        abort(403)
    admins = Admin.query.order_by(Admin.created_at.desc()).all()
    return render_template("admins_list.html", admins=admins)


@app.route("/admins/create", methods=["GET", "POST"])
@login_required
def admin_create() -> str | Response:
    """Create a new admin account.

    Only super admins may create new admins. The creating admin may assign the
    new admin to a clinic or mark them as super.
    """
    admin = current_admin()
    if not admin or not admin.is_superadmin:
        abort(403)
    clinics = Clinic.query.all()
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        clinic_id = request.form.get("clinic_id")
        is_super = bool(request.form.get("is_superadmin"))
        if not username or not password:
            flash("Username and password are required.")
            return render_template(
                "admin_form.html", admin=None, clinics=clinics, form=request.form
            )
        if Admin.query.filter_by(username=username).first():
            flash("An admin with that username already exists.")
            return render_template(
                "admin_form.html", admin=None, clinics=clinics, form=request.form
            )
        new_admin = Admin(
            username=username,
            clinic_id=int(clinic_id) if clinic_id else None,
            is_superadmin=is_super,
        )
        new_admin.set_password(password)
        db.session.add(new_admin)
        db.session.commit()
        flash("Admin created successfully.")
        return redirect(url_for("admins_list"))
    return render_template("admin_form.html", admin=None, clinics=clinics)


@app.route("/admins/<int:admin_id>/edit", methods=["GET", "POST"])
@login_required
def admin_edit(admin_id: int) -> str | Response:
    """Edit an existing admin account.

    Only super admins may edit other admins. They can change username, reset
    password, assign or remove a clinic, and toggle super admin status.
    """
    admin = current_admin()
    if not admin or not admin.is_superadmin:
        abort(403)
    edit_admin = Admin.query.get_or_404(admin_id)
    clinics = Clinic.query.all()
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        clinic_id = request.form.get("clinic_id")
        is_super = bool(request.form.get("is_superadmin"))
        if not username:
            flash("Username is required.")
            return render_template(
                "admin_form.html",
                admin=edit_admin,
                clinics=clinics,
                form=request.form,
            )
        # Check for username collisions
        existing = Admin.query.filter_by(username=username).first()
        if existing and existing.id != edit_admin.id:
            flash("Another admin with that username already exists.")
            return render_template(
                "admin_form.html",
                admin=edit_admin,
                clinics=clinics,
                form=request.form,
            )
        edit_admin.username = username
        edit_admin.clinic_id = int(clinic_id) if clinic_id else None
        edit_admin.is_superadmin = is_super
        if password:
            edit_admin.set_password(password)
        db.session.commit()
        flash("Admin updated successfully.")
        return redirect(url_for("admins_list"))
    return render_template("admin_form.html", admin=edit_admin, clinics=clinics)


@app.route("/admins/<int:admin_id>/delete", methods=["POST"])
@login_required
def admin_delete(admin_id: int) -> Response:
    """Delete an admin account.

    Super admins may delete other admins. They cannot delete themselves to
    prevent locking themselves out.
    """
    admin = current_admin()
    if not admin or not admin.is_superadmin:
        abort(403)
    if admin.id == admin_id:
        flash("You cannot delete yourself.")
        return redirect(url_for("admins_list"))
    del_admin = Admin.query.get_or_404(admin_id)
    db.session.delete(del_admin)
    db.session.commit()
    flash("Admin deleted successfully.")
    return redirect(url_for("admins_list"))


###############################################################################
# Routes: API key management
###############################################################################


@app.route("/clinics/<slug>/api-keys", methods=["GET", "POST"])
@login_required
def api_keys(slug: str) -> str | Response:
    """Display and create API keys for a clinic.

    Admins associated with a clinic or super admins may access this page. On
    POST a new random key is generated and stored. The generated key is
    displayed only once to the admin and then persisted. Note that keys are
    stored in plaintext for simplicity. In a real system consider storing
    hashes instead.
    """
    clinic = Clinic.query.filter_by(slug=slug).first_or_404()
    admin = current_admin()
    if not admin:
        abort(403)
    if not admin.is_superadmin and admin.clinic_id != clinic.id:
        abort(403)
    if request.method == "POST":
        name = request.form.get("name") or "Unnamed key"
        # Generate a sufficiently long urlsafe key
        key_value = secrets.token_urlsafe(32)
        api_key = ApiKey(clinic=clinic, name=name, key=key_value)
        db.session.add(api_key)
        db.session.commit()
        flash(f"Created API key: {key_value}. Make sure to copy it now.")
        return redirect(url_for("api_keys", slug=slug))
    return render_template("api_keys.html", clinic=clinic)


@app.route("/clinics/<slug>/api-keys/<int:key_id>/revoke", methods=["POST"])
@login_required
def api_key_revoke(slug: str, key_id: int) -> Response:
    """Disable an existing API key.

    Rather than deleting keys we simply set is_active to False. This way
    historical data remains intact. Only admins bound to the clinic or super
    admins may revoke keys.
    """
    clinic = Clinic.query.filter_by(slug=slug).first_or_404()
    admin = current_admin()
    if not admin:
        abort(403)
    if not admin.is_superadmin and admin.clinic_id != clinic.id:
        abort(403)
    api_key = ApiKey.query.filter_by(id=key_id, clinic_id=clinic.id).first_or_404()
    api_key.is_active = False
    db.session.commit()
    flash("API key revoked.")
    return redirect(url_for("api_keys", slug=slug))


###############################################################################
# Routes: SMS handling (unchanged but consolidated here)
###############################################################################


@app.route("/t/<slug>/sms/inbound", methods=["POST"])
def sms_inbound(slug: str) -> Response:
    """Twilio webhook for inbound SMS.

    Logs the message in SmsLog and optionally sends an automated reply. If
    Twilio credentials are configured a reply will be sent via the Twilio
    client. Otherwise only the log entry is recorded.
    """
    clinic = Clinic.query.filter_by(slug=slug).first()
    if not clinic:
        # Unknown clinic slug results in a generic reply without logging
        response = MessagingResponse() if MessagingResponse else None
        if response:
            response.message("Unknown clinic.")
            return Response(str(response), mimetype="application/xml")
        return Response("", mimetype="text/plain")
    from_number = request.form.get("From")
    to_number = request.form.get("To")
    body = request.form.get("Body")
    direction = request.form.get("Direction", "inbound")
    status = request.form.get("SmsStatus")
    sms_log = SmsLog(
        clinic=clinic,
        from_number=from_number or "",
        to_number=to_number or "",
        body=body or "",
        direction=direction or "",
        status=status,
    )
    db.session.add(sms_log)
    db.session.commit()
    # Optionally send an automated acknowledgement
    response = MessagingResponse() if MessagingResponse else None
    if response:
        response.message(f"Thank you for texting {clinic.name}. We will respond shortly.")
        return Response(str(response), mimetype="application/xml")
    return Response("", mimetype="text/plain")


###############################################################################
# Routes: Voice/call handling
###############################################################################


@app.route("/t/<slug>/voice/inbound", methods=["POST"])
def voice_inbound(slug: str) -> Response:
    """Twilio webhook for inbound voice calls.

    Logs call metadata and responds with a simple TwiML message. A status
    callback should be configured on the Twilio number to hit
    ``/t/<slug>/voice/status`` to update the call log with duration and final
    status. Without Twilio the response is a plain text string.
    """
    clinic = Clinic.query.filter_by(slug=slug).first_or_404()
    from_number = request.form.get("From") or ""
    to_number = request.form.get("To") or ""
    call_sid = request.form.get("CallSid")
    direction = request.form.get("Direction", "inbound")
    # Create call log record
    call_log = CallLog(
        clinic=clinic,
        call_sid=call_sid,
        from_number=from_number,
        to_number=to_number,
        direction=direction,
        start_time=datetime.utcnow(),
        status=request.form.get("CallStatus"),
    )
    db.session.add(call_log)
    db.session.commit()
    # Build TwiML response
    if VoiceResponse:
        vr = VoiceResponse()
        vr.say(f"Thank you for calling {clinic.name}. Please leave a message after the beep.")
        vr.record(max_length=120)
        return Response(str(vr), mimetype="application/xml")
    else:
        return Response("Thanks for calling.", mimetype="text/plain")


@app.route("/t/<slug>/voice/status", methods=["POST"])
def voice_status(slug: str) -> Response:
    """Status callback for voice calls.

    Updates an existing CallLog with the final status, duration and end time.
    This route can be configured in Twilio under the Voice settings for the
    phone number using the "Status Callback URL" field.
    """
    clinic = Clinic.query.filter_by(slug=slug).first_or_404()
    call_sid = request.form.get("CallSid")
    log = CallLog.query.filter_by(call_sid=call_sid, clinic_id=clinic.id).first()
    if log:
        log.status = request.form.get("CallStatus")
        duration = request.form.get("CallDuration")
        if duration and duration.isdigit():
            log.duration = int(duration)
        log.end_time = datetime.utcnow()
        db.session.commit()
    return Response("", status=204)


###############################################################################
# Routes: Generic call log ingestion
###############################################################################

@app.route("/api/log-call", methods=["POST"])
def log_call_api() -> Response:
    """API endpoint to log call data with an AI generated summary.

    This endpoint is designed for integrations such as n8n or other external
    services to record call interactions directly into the database. It
    expects a JSON payload with the following fields:

      - ``clinic_id`` (int): ID of the clinic the call belongs to.
      - ``patient_message`` (str): Raw transcript or message text from the caller.
      - ``ai_summary`` (str): AI‑generated summary of the call.

    The incoming data is validated and then stored in the CallLog table. The
    summary and transcript are concatenated and stored in the ``notes`` column
    of the CallLog. The created log's ID is returned in the JSON response.
    On error (missing fields or invalid clinic), a 400 response is returned.
    """
    data = request.get_json(silent=True) or {}
    clinic_id = data.get("clinic_id")
    patient_message = data.get("patient_message")
    ai_summary = data.get("ai_summary")
    # Require all fields
    if not clinic_id or not patient_message or not ai_summary:
        return (
            jsonify(
                {
                    "error": "clinic_id, patient_message and ai_summary are required",
                }
            ),
            400,
        )
    # Fetch clinic; 404 if not found
    clinic = Clinic.query.get_or_404(int(clinic_id))

    # Optional API key enforcement. When REQUIRE_API_KEY is set to "true" in
    # the environment, this endpoint expects a valid API key to be provided
    # either in the Authorization header using the Bearer scheme or as a
    # field in the JSON payload. The key must correspond to an active ApiKey
    # associated with the target clinic. If authentication fails the
    # request is rejected with a 401 error and no data is persisted.
    if os.environ.get("REQUIRE_API_KEY", "false").lower() == "true":
        # Extract token from Authorization header or JSON body
        auth_header = request.headers.get("Authorization", "")
        token = None
        if auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1].strip()
        if not token:
            token = data.get("api_key")
        if not token:
            return (
                jsonify({"error": "Missing API key"}),
                401,
            )
        api_key_obj = ApiKey.query.filter_by(
            key=token, clinic_id=clinic.id, is_active=True
        ).first()
        if not api_key_obj:
            return (
                jsonify({"error": "Invalid or inactive API key"}),
                401,
            )

    # Build call log. We intentionally leave call_sid, from/to numbers empty as
    # they may not be relevant for AI summaries. Direction is set to inbound
    # by default. Notes stores both the transcript and the summary.
    notes = f"Transcript: {patient_message}\nAI Summary: {ai_summary}"
    log_entry = CallLog(
        clinic=clinic,
        call_sid=None,
        from_number="",
        to_number="",
        direction="inbound",
        status=None,
        start_time=datetime.utcnow(),
        notes=notes,
    )
    db.session.add(log_entry)
    db.session.commit()
    return jsonify({"id": log_entry.id, "message": "Call log created"}), 201


###############################################################################
# Routes: Global Twilio webhooks (SMS and voice)
###############################################################################


@app.route("/twilio/sms", methods=["POST"])
def twilio_sms_global() -> Response:
    """Handle inbound SMS messages for the default clinic.

    This route allows you to configure a single Twilio number to point at
    ``/twilio/sms`` without specifying a clinic slug. It will look up the
    first configured clinic in the database and log the message as a call
    interaction, generating an AI summary where possible. A concise reply
    containing the summary is returned to the caller via TwiML. If no clinic
    exists in the database a generic response is sent.
    """
    # Fetch the first clinic (ordered by creation). If no clinic is found
    # return an informative response.
    clinic = Clinic.query.order_by(Clinic.id).first()
    if not clinic:
        # Build a simple response indicating no clinic configured.
        if MessagingResponse:
            resp = MessagingResponse()
            resp.message("No clinic is configured. Please set up a clinic first.")
            return Response(str(resp), mimetype="application/xml")
        return Response("No clinic configured.", mimetype="text/plain")
    # Extract relevant Twilio parameters from the inbound request.
    from_number = request.form.get("From") or ""
    to_number = request.form.get("To") or ""
    body = request.form.get("Body") or ""
    # Generate an AI summary of the message. Falls back to truncation if
    # OpenAI is unavailable or misconfigured.
    summary = generate_summary(body)
    # Create a call log entry to persist the transcript and summary in the
    # notes field. We treat SMS interactions as inbound calls for the purposes
    # of summarisation. The direction is set to inbound, call_sid is None.
    notes = f"Transcript: {body}\nAI Summary: {summary}"
    call_log = CallLog(
        clinic=clinic,
        call_sid=None,
        from_number=from_number,
        to_number=to_number,
        direction="inbound",
        status=None,
        start_time=datetime.utcnow(),
        notes=notes,
    )
    db.session.add(call_log)
    db.session.commit()
    # Build TwiML response. If the Twilio helper library is available,
    # respond with XML instructing Twilio to send the summary. Otherwise
    # return plain text.
    if MessagingResponse:
        resp = MessagingResponse()
        resp.message(f"Thanks! Summary: {summary}")
        return Response(str(resp), mimetype="application/xml")
    return Response(f"Thanks! Summary: {summary}", mimetype="text/plain")


@app.route("/twilio/voice", methods=["POST"])
def twilio_voice_global() -> Response:
    """Handle inbound voice calls for the default clinic.

    When a call comes in, this route logs basic call metadata and instructs
    the caller to leave a voicemail. The voice recording will be sent to
    your Twilio console and can be processed separately (e.g. using the
    ``/api/log-call`` endpoint or another transcription service). If no
    clinic exists, a plain text response is returned.
    """
    clinic = Clinic.query.order_by(Clinic.id).first()
    if not clinic:
        # No clinic configured. Respond politely.
        if VoiceResponse:
            vr = VoiceResponse()
            vr.say("No clinic is configured. Please contact the administrator.")
            return Response(str(vr), mimetype="application/xml")
        return Response("No clinic configured.", mimetype="text/plain")
    # Extract parameters
    from_number = request.form.get("From") or ""
    to_number = request.form.get("To") or ""
    call_sid = request.form.get("CallSid")
    direction = request.form.get("Direction", "inbound")
    # Create call log entry with start time. End time and duration will be
    # filled in by the status callback (see /t/<slug>/voice/status) if used.
    log_entry = CallLog(
        clinic=clinic,
        call_sid=call_sid,
        from_number=from_number,
        to_number=to_number,
        direction=direction,
        start_time=datetime.utcnow(),
        status=request.form.get("CallStatus"),
    )
    db.session.add(log_entry)
    db.session.commit()
    # Respond with TwiML instructing caller to leave a voicemail. We reuse
    # Twilio's ``record`` verb to record up to 120 seconds. If Twilio helper
    # library isn't available we return plain text instead.
    if VoiceResponse:
        vr = VoiceResponse()
        vr.say(f"Thank you for calling {clinic.name}. Please leave a message after the beep.")
        vr.record(max_length=120)
        return Response(str(vr), mimetype="application/xml")
    else:
        return Response("Thank you for calling. Please leave a message.", mimetype="text/plain")


###############################################################################
# CLI: Create clinics
#
# Provides a simple Flask CLI command for creating clinics from the command
# line. Use ``flask create-clinic`` with environment variables to set
# credentials. This helper is retained from previous iterations for convenience.
###############################################################################


@app.cli.command("create-clinic")
def create_clinic_command() -> None:
    """Create a clinic using environment variables.

    This command makes it easy to bootstrap a clinic entry without having to
    open the database manually. It reads CLINIC_SLUG, CLINIC_NAME and optional
    TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER from the
    environment. Encryption is handled automatically if APP_ENC_KEY is set.
    """
    slug = os.environ.get("CLINIC_SLUG")
    name = os.environ.get("CLINIC_NAME")
    if not slug or not name:
        print("CLINIC_SLUG and CLINIC_NAME environment variables are required.")
        return
    if Clinic.query.filter_by(slug=slug).first():
        print(f"Clinic with slug {slug} already exists.")
        return
    clinic = Clinic(slug=slug, name=name)
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_number = os.environ.get("TWILIO_FROM_NUMBER")
    f = get_fernet()
    if account_sid and auth_token and f:
        clinic.twilio_account_sid_encrypted = f.encrypt(account_sid.encode())
        clinic.twilio_auth_token_encrypted = f.encrypt(auth_token.encode())
        clinic.twilio_from_number = from_number
    db.session.add(clinic)
    db.session.commit()
    print(f"Clinic {slug} created successfully.")

# ---------------------------------------------------------------------------
# One‑time setup route
#
# This endpoint allows the application to bootstrap its first clinic and
# administrator when shell access is unavailable (e.g. in certain PaaS
# environments). To protect against unauthorised creation, set the
# environment variable ``SETUP_TOKEN`` to a secret value and include it
# as a ``token`` query parameter in your request. The route will do
# nothing if an admin or clinic already exists. After creation you should
# remove or unset the ``SETUP_TOKEN`` variable and redeploy the app.
@app.route("/setup", methods=["POST", "GET"])
def setup_route() -> Response:
    # Only allow if a setup token is configured
    setup_token = os.environ.get("SETUP_TOKEN")
    if not setup_token:
        return jsonify({"error": "Setup is disabled"}), 403
    # Accept token from query string or form body
    token = request.args.get("token") or request.form.get("token")
    if token != setup_token:
        return jsonify({"error": "Invalid setup token"}), 403
    # Prevent reinitialisation if data already exists
    if Admin.query.first() or Clinic.query.first():
        return jsonify({"error": "Already initialised"}), 400
    # Read initial admin and clinic details from environment variables
    admin_username = os.environ.get("INIT_ADMIN_USERNAME", "admin")
    admin_email = os.environ.get("INIT_ADMIN_EMAIL", "admin@example.com")
    admin_password = os.environ.get("INIT_ADMIN_PASSWORD", "changeme")
    clinic_slug = os.environ.get("INIT_CLINIC_SLUG", "default")
    clinic_name = os.environ.get("INIT_CLINIC_NAME", "Default Clinic")
    twilio_sid = os.environ.get("INIT_TWILIO_ACCOUNT_SID")
    twilio_token = os.environ.get("INIT_TWILIO_AUTH_TOKEN")
    twilio_number = os.environ.get("INIT_TWILIO_FROM_NUMBER")
    # Create clinic
    clinic = Clinic(slug=clinic_slug, name=clinic_name)
    f = get_fernet()
    if twilio_sid and twilio_token and f:
        clinic.twilio_account_sid_encrypted = f.encrypt(twilio_sid.encode())
        clinic.twilio_auth_token_encrypted = f.encrypt(twilio_token.encode())
        clinic.twilio_from_number = twilio_number
    db.session.add(clinic)
    db.session.commit()
    # Create admin
    admin = Admin(username=admin_username, is_superadmin=True, clinic_id=None)
    admin.set_password(admin_password)
    # Optionally set email attribute if model has one (backwards compatibility)
    if hasattr(admin, "email"):
        setattr(admin, "email", admin_email)  # type: ignore[attr-defined]
    db.session.add(admin)
    db.session.commit()
    return jsonify({
        "message": "Initial clinic and admin created successfully",
        "clinic_slug": clinic.slug,
        "admin_username": admin.username,
    }), 201
