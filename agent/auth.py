"""Authentication: passwords (bcrypt), sessions, account lockout, login routes.

This is a v0 demo auth system standing in for the architectural target of
OpenEMR's OAuth2/SMART-on-FHIR (see ARCHITECTURE.md). When OpenEMR is
deployed, this module is replaced by an OAuth2 client.
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import bcrypt
import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from agent import audit, email as email_module
from agent.config import Config, get_config
from agent.db import connect


# --- Constants ---

IDLE_TIMEOUT_SECONDS = 300            # 5 minutes
ABSOLUTE_TIMEOUT_SECONDS = 28_800     # 8 hours
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_SECONDS = 900        # 15 minutes
MFA_PENDING_WINDOW_SECONDS = 300      # 5 minutes to complete MFA after password
TOTP_ISSUER = "Clinical Co-Pilot"
PASSWORD_RESET_TOKEN_TTL_SECONDS = 3600  # 1 hour
PASSWORD_MIN_LENGTH = 8


# --- Domain ---

@dataclass
class User:
    id: int
    username: str
    email: str
    role: str
    is_active: bool
    failed_login_attempts: int
    locked_until: datetime | None
    totp_enrolled: bool

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "User":
        return cls(
            id=row["id"],
            username=row["username"],
            email=row["email"],
            role=row["role"],
            is_active=bool(row["is_active"]),
            failed_login_attempts=row["failed_login_attempts"],
            locked_until=_parse_dt(row["locked_until"]),
            totp_enrolled=bool(row["totp_enrolled"]),
        )

    def is_locked(self, now: datetime | None = None) -> bool:
        if self.locked_until is None:
            return False
        return (now or _now()) < self.locked_until


# --- Password hashing ---

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# --- DB helpers ---

def get_user_by_username(database_url: str, username: str) -> User | None:
    with connect(database_url) as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
    return User.from_row(row) if row else None


def get_user_by_email(database_url: str, email: str) -> User | None:
    with connect(database_url) as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
    return User.from_row(row) if row else None


def get_user_by_id(database_url: str, user_id: int) -> User | None:
    with connect(database_url) as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    return User.from_row(row) if row else None


def _password_hash_for_user(database_url: str, user_id: int) -> str | None:
    with connect(database_url) as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    return row["password_hash"] if row else None


def create_user(
    database_url: str,
    *,
    username: str,
    email: str,
    password: str,
    role: str = "physician",
) -> User:
    pwd_hash = hash_password(password)
    with connect(database_url) as conn:
        cur = conn.execute(
            """INSERT INTO users (username, email, password_hash, role)
               VALUES (?, ?, ?, ?)""",
            (username, email, pwd_hash, role),
        )
        user_id = cur.lastrowid
        conn.commit()
    audit.record(
        database_url,
        audit.AuditEvent.USER_CREATED,
        user_id=user_id,
        details={"username": username, "email": email, "role": role},
    )
    user = get_user_by_id(database_url, user_id)
    assert user is not None
    return user


def _record_failed_login(database_url: str, user: User) -> User:
    new_attempts = user.failed_login_attempts + 1
    locked_until: datetime | None = None
    if new_attempts >= MAX_FAILED_ATTEMPTS:
        locked_until = _now() + timedelta(seconds=LOCKOUT_DURATION_SECONDS)
    with connect(database_url) as conn:
        conn.execute(
            """UPDATE users
               SET failed_login_attempts = ?,
                   locked_until = ?,
                   updated_at = datetime('now')
               WHERE id = ?""",
            (new_attempts, _format_dt(locked_until), user.id),
        )
        conn.commit()
    if locked_until is not None:
        audit.record(
            database_url,
            audit.AuditEvent.ACCOUNT_LOCKED,
            user_id=user.id,
            details={
                "attempts": new_attempts,
                "locked_until": _format_dt(locked_until),
            },
        )
    refreshed = get_user_by_id(database_url, user.id)
    assert refreshed is not None
    return refreshed


def _record_successful_login(database_url: str, user: User) -> None:
    with connect(database_url) as conn:
        conn.execute(
            """UPDATE users
               SET failed_login_attempts = 0,
                   locked_until = NULL,
                   updated_at = datetime('now')
               WHERE id = ?""",
            (user.id,),
        )
        conn.commit()


def _save_totp_secret(database_url: str, user_id: int, secret: str) -> None:
    with connect(database_url) as conn:
        conn.execute(
            """UPDATE users
               SET totp_secret = ?,
                   totp_enrolled = 1,
                   updated_at = datetime('now')
               WHERE id = ?""",
            (secret, user_id),
        )
        conn.commit()


def reset_mfa(database_url: str, user_id: int) -> None:
    """Admin operation: clear TOTP enrollment so user must re-enroll on next login."""
    with connect(database_url) as conn:
        conn.execute(
            """UPDATE users
               SET totp_secret = NULL,
                   totp_enrolled = 0,
                   updated_at = datetime('now')
               WHERE id = ?""",
            (user_id,),
        )
        conn.commit()


def _user_totp_secret(database_url: str, user_id: int) -> str | None:
    with connect(database_url) as conn:
        row = conn.execute(
            "SELECT totp_secret FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    return row["totp_secret"] if row else None


# --- TOTP helpers ---

def generate_totp_secret() -> str:
    return pyotp.random_base32()


def totp_provisioning_uri(user: User, secret: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(
        name=user.email,
        issuer_name=TOTP_ISSUER,
    )


def verify_totp(secret: str, code: str) -> bool:
    if not secret or not code:
        return False
    code_clean = code.strip().replace(" ", "")
    if not code_clean.isdigit() or len(code_clean) != 6:
        return False
    return pyotp.TOTP(secret).verify(code_clean, valid_window=1)


# --- Datetime helpers (UTC, ISO 8601) ---

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _format_dt(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).isoformat()


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    # SQLite default datetime() returns naive UTC; isoformat() is timezone-aware.
    # Handle both shapes.
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# --- Session helpers ---

def _set_session(request: Request, user_id: int) -> None:
    request.session.clear()
    request.session["user_id"] = user_id
    request.session["last_activity"] = _now().isoformat()
    request.session["login_at"] = _now().isoformat()


def _clear_session(request: Request) -> None:
    request.session.clear()


# --- Pending-MFA helpers (after password verification, before MFA verification) ---

def _set_pending_mfa(request: Request, user_id: int, *, totp_secret: str | None = None) -> None:
    request.session.clear()
    request.session["pending_mfa_user_id"] = user_id
    request.session["pending_mfa_until"] = (
        _now() + timedelta(seconds=MFA_PENDING_WINDOW_SECONDS)
    ).isoformat()
    if totp_secret:
        request.session["pending_mfa_secret"] = totp_secret


def _get_pending_mfa_user_id(request: Request) -> int | None:
    user_id = request.session.get("pending_mfa_user_id")
    until = _parse_dt(request.session.get("pending_mfa_until"))
    if not user_id or not until or _now() > until:
        return None
    return user_id


def _get_pending_mfa_secret(request: Request) -> str | None:
    return request.session.get("pending_mfa_secret")


def _get_authenticated_user_id(request: Request, config: Config) -> int | None:
    """Return user_id from session, or None if missing / idle-expired / absolute-expired.
    Side-effect: clears the session and records audit event on expiry."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None

    last_activity_str = request.session.get("last_activity")
    login_at_str = request.session.get("login_at")
    last_activity = _parse_dt(last_activity_str) if last_activity_str else None
    login_at = _parse_dt(login_at_str) if login_at_str else None

    if last_activity is None or login_at is None:
        _clear_session(request)
        return None

    now = _now()
    if (now - last_activity).total_seconds() > IDLE_TIMEOUT_SECONDS:
        audit.record(
            config.database_url,
            audit.AuditEvent.SESSION_EXPIRED,
            user_id=user_id,
            details={"reason": "idle_timeout"},
        )
        _clear_session(request)
        return None

    if (now - login_at).total_seconds() > ABSOLUTE_TIMEOUT_SECONDS:
        audit.record(
            config.database_url,
            audit.AuditEvent.SESSION_EXPIRED,
            user_id=user_id,
            details={"reason": "absolute_timeout"},
        )
        _clear_session(request)
        return None

    # Activity bump.
    request.session["last_activity"] = now.isoformat()
    return user_id


# --- FastAPI dependency ---

def get_current_user(
    request: Request,
    config: Config = Depends(get_config),
) -> User:
    user_id = _get_authenticated_user_id(request, config)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": 'Cookie realm="agent"'},
        )
    user = get_user_by_id(config.database_url, user_id)
    if user is None or not user.is_active:
        _clear_session(request)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return user


# --- Schemas ---

class LoginIn(BaseModel):
    username: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1, max_length=512)


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    role: str
    totp_enrolled: bool


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        totp_enrolled=user.totp_enrolled,
    )


class LoginOut(BaseModel):
    user: UserOut | None = None
    needs_mfa: bool = False
    mfa_action: str | None = None  # "enroll" | "challenge"


class MfaSetupOut(BaseModel):
    provisioning_uri: str
    secret: str  # exposed once for manual-entry fallback; persisted only after verify-setup
    issuer: str
    account_name: str


class MfaCodeIn(BaseModel):
    code: str = Field(..., min_length=6, max_length=10)


class PasswordResetRequestIn(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)


class PasswordResetConfirmIn(BaseModel):
    token: str = Field(..., min_length=20, max_length=512)
    new_password: str = Field(
        ..., min_length=PASSWORD_MIN_LENGTH, max_length=512
    )


# --- Routes ---

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginOut)
def login(
    payload: LoginIn,
    request: Request,
    response: Response,
    config: Config = Depends(get_config),
) -> LoginOut:
    ip = _client_ip(request)
    user = get_user_by_username(config.database_url, payload.username)

    if user is None:
        audit.record(
            config.database_url,
            audit.AuditEvent.LOGIN_FAILED_NO_USER,
            ip_address=ip,
            details={"username": payload.username},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    if not user.is_active:
        audit.record(
            config.database_url,
            audit.AuditEvent.LOGIN_FAILED_INACTIVE,
            user_id=user.id,
            ip_address=ip,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is inactive.",
        )

    if user.is_locked():
        audit.record(
            config.database_url,
            audit.AuditEvent.LOGIN_FAILED_LOCKED,
            user_id=user.id,
            ip_address=ip,
            details={"locked_until": _format_dt(user.locked_until)},
        )
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=(
                "Account temporarily locked due to too many failed login attempts. "
                "Please try again later."
            ),
        )

    pwd_hash = _password_hash_for_user(config.database_url, user.id)
    if pwd_hash is None or not verify_password(payload.password, pwd_hash):
        user = _record_failed_login(config.database_url, user)
        audit.record(
            config.database_url,
            audit.AuditEvent.LOGIN_FAILED_BAD_PASSWORD,
            user_id=user.id,
            ip_address=ip,
            details={"attempts": user.failed_login_attempts},
        )
        if user.is_locked():
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=(
                    "Too many failed attempts. Account locked for 15 minutes."
                ),
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    # Password verified. Reset password failure counter, then route through MFA.
    _record_successful_login(config.database_url, user)

    refreshed = get_user_by_id(config.database_url, user.id)
    assert refreshed is not None

    _set_pending_mfa(request, refreshed.id)
    if refreshed.totp_enrolled:
        return LoginOut(needs_mfa=True, mfa_action="challenge")
    # Not yet enrolled — force MFA enrollment before granting access.
    return LoginOut(needs_mfa=True, mfa_action="enroll")


# --- MFA endpoints ---

def _require_pending_mfa(request: Request) -> int:
    user_id = _get_pending_mfa_user_id(request)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="MFA window expired. Please sign in again.",
        )
    return user_id


@router.post("/mfa/setup", response_model=MfaSetupOut)
def mfa_setup(
    request: Request,
    config: Config = Depends(get_config),
) -> MfaSetupOut:
    # Allow setup either while pending (first-time enrollment) or while fully
    # authenticated (re-enrollment from a logged-in user).
    user_id = _get_pending_mfa_user_id(request) or request.session.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
        )
    user = get_user_by_id(config.database_url, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
        )

    secret = generate_totp_secret()
    # Stash secret in session; only persisted after the user proves they can compute codes.
    request.session["pending_mfa_secret"] = secret
    if "pending_mfa_user_id" not in request.session:
        # Fully-authenticated re-enrollment path: remember which user is enrolling.
        request.session["pending_mfa_user_id"] = user.id
        request.session["pending_mfa_until"] = (
            _now() + timedelta(seconds=MFA_PENDING_WINDOW_SECONDS)
        ).isoformat()

    audit.record(
        config.database_url,
        audit.AuditEvent.MFA_ENROLLMENT_STARTED,
        user_id=user.id,
        ip_address=_client_ip(request),
    )
    return MfaSetupOut(
        provisioning_uri=totp_provisioning_uri(user, secret),
        secret=secret,
        issuer=TOTP_ISSUER,
        account_name=user.email,
    )


@router.post("/mfa/verify-setup", response_model=LoginOut)
def mfa_verify_setup(
    payload: MfaCodeIn,
    request: Request,
    config: Config = Depends(get_config),
) -> LoginOut:
    user_id = _require_pending_mfa(request)
    secret = _get_pending_mfa_secret(request)
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No MFA setup in progress. Start enrollment again.",
        )
    if not verify_totp(secret, payload.code):
        audit.record(
            config.database_url,
            audit.AuditEvent.MFA_FAILED,
            user_id=user_id,
            ip_address=_client_ip(request),
            details={"phase": "enrollment"},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That code doesn't match. Check the time on your device and try again.",
        )

    _save_totp_secret(config.database_url, user_id, secret)
    audit.record(
        config.database_url,
        audit.AuditEvent.MFA_ENROLLED,
        user_id=user_id,
        ip_address=_client_ip(request),
    )
    _set_session(request, user_id)
    audit.record(
        config.database_url,
        audit.AuditEvent.LOGIN_SUCCESS,
        user_id=user_id,
        ip_address=_client_ip(request),
        details={"via": "mfa_enrollment"},
    )
    user = get_user_by_id(config.database_url, user_id)
    assert user is not None
    return LoginOut(user=_user_out(user), needs_mfa=False)


# --- Password reset ---

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@router.post("/password-reset/request")
async def password_reset_request(
    payload: PasswordResetRequestIn,
    request: Request,
    config: Config = Depends(get_config),
) -> dict[str, str]:
    """Request a password-reset email. Returns 200 unconditionally to avoid
    leaking whether an account exists for that address."""
    ip = _client_ip(request)
    email_normalized = payload.email.strip().lower()
    user = get_user_by_email(config.database_url, email_normalized)

    response: dict[str, str] = {"status": "ok"}

    if user is None or not user.is_active:
        audit.record(
            config.database_url,
            audit.AuditEvent.PASSWORD_RESET_REQUESTED,
            ip_address=ip,
            details={"email": email_normalized, "result": "no_active_user"},
        )
        return response

    token = secrets.token_urlsafe(32)
    token_hash = _hash_token(token)
    expires_at = _now() + timedelta(seconds=PASSWORD_RESET_TOKEN_TTL_SECONDS)

    with connect(config.database_url) as conn:
        conn.execute(
            """INSERT INTO password_reset_tokens (user_id, token_hash, expires_at)
               VALUES (?, ?, ?)""",
            (user.id, token_hash, _format_dt(expires_at)),
        )
        conn.commit()

    audit.record(
        config.database_url,
        audit.AuditEvent.PASSWORD_RESET_REQUESTED,
        user_id=user.id,
        ip_address=ip,
    )

    reset_url = f"{config.app_base_url.rstrip('/')}/?reset_token={token}"
    try:
        await email_module.send_password_reset_email(
            api_key=config.resend_api_key,
            from_addr=config.resend_from,
            to_addr=user.email,
            reset_url=reset_url,
        )
    except email_module.EmailSendError:
        # Swallow — don't leak delivery failure to caller. Log was already done.
        pass

    return response


@router.post("/password-reset/confirm")
def password_reset_confirm(
    payload: PasswordResetConfirmIn,
    request: Request,
    config: Config = Depends(get_config),
) -> dict[str, str]:
    token_hash = _hash_token(payload.token)
    ip = _client_ip(request)

    with connect(config.database_url) as conn:
        row = conn.execute(
            """SELECT id, user_id, expires_at, used_at
               FROM password_reset_tokens
               WHERE token_hash = ?""",
            (token_hash,),
        ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link is not valid. Request a new one.",
        )

    if row["used_at"] is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link has already been used. Request a new one.",
        )

    expires_at = _parse_dt(row["expires_at"])
    if expires_at is None or _now() > expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link has expired. Request a new one.",
        )

    user = get_user_by_id(config.database_url, row["user_id"])
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This account is no longer active.",
        )

    new_hash = hash_password(payload.new_password)
    with connect(config.database_url) as conn:
        conn.execute(
            """UPDATE users
               SET password_hash = ?,
                   failed_login_attempts = 0,
                   locked_until = NULL,
                   updated_at = datetime('now')
               WHERE id = ?""",
            (new_hash, user.id),
        )
        conn.execute(
            """UPDATE password_reset_tokens
               SET used_at = datetime('now')
               WHERE id = ?""",
            (row["id"],),
        )
        conn.commit()

    audit.record(
        config.database_url,
        audit.AuditEvent.PASSWORD_RESET_COMPLETED,
        user_id=user.id,
        ip_address=ip,
    )

    return {"status": "ok"}


@router.post("/mfa/challenge", response_model=LoginOut)
def mfa_challenge(
    payload: MfaCodeIn,
    request: Request,
    config: Config = Depends(get_config),
) -> LoginOut:
    user_id = _require_pending_mfa(request)
    secret = _user_totp_secret(config.database_url, user_id)
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA not enrolled. Sign in again to enroll.",
        )
    if not verify_totp(secret, payload.code):
        audit.record(
            config.database_url,
            audit.AuditEvent.MFA_FAILED,
            user_id=user_id,
            ip_address=_client_ip(request),
            details={"phase": "challenge"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid code.",
        )

    _set_session(request, user_id)
    audit.record(
        config.database_url,
        audit.AuditEvent.MFA_VERIFIED,
        user_id=user_id,
        ip_address=_client_ip(request),
    )
    audit.record(
        config.database_url,
        audit.AuditEvent.LOGIN_SUCCESS,
        user_id=user_id,
        ip_address=_client_ip(request),
        details={"via": "mfa_challenge"},
    )
    user = get_user_by_id(config.database_url, user_id)
    assert user is not None
    return LoginOut(user=_user_out(user), needs_mfa=False)


@router.post("/logout")
def logout(
    request: Request,
    config: Config = Depends(get_config),
) -> dict[str, str]:
    user_id = request.session.get("user_id")
    _clear_session(request)
    if user_id:
        audit.record(
            config.database_url,
            audit.AuditEvent.LOGOUT,
            user_id=user_id,
            ip_address=_client_ip(request),
        )
    return {"status": "ok"}


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> UserOut:
    return _user_out(current_user)


def _client_ip(request: Request) -> str | None:
    # Honor X-Forwarded-For when present (Railway sits behind a proxy).
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else None
