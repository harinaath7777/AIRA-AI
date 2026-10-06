# auth.py
# Authentication layer: user management, password hashing,
# JWT creation/verification, and server-side token blacklisting.

import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

# ── JWT deps ──────────────────────────────────────────────────
import jwt as _jwt  # PyJWT (installed with flask-jwt-extended)

import os

# ── Config ────────────────────────────────────────────────────
SECRET_KEY   = os.environ.get("AIRA_SECRET_KEY", "aira-research-agent-secret-key-hs256-persistent-2026")
ALGORITHM    = "HS256"
ACCESS_TTL   = timedelta(hours=8)      # access token lifetime
REFRESH_TTL  = timedelta(days=30)      # refresh token lifetime

AUTH_DB_PATH = Path(__file__).parent / "auth.db"


# ══════════════════════════════════════════════════════════════
# DATABASE SETUP
# ══════════════════════════════════════════════════════════════

def _conn():
    c = sqlite3.connect(str(AUTH_DB_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def init_auth_db():
    """Create users and blacklist tables."""
    conn = _conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT    NOT NULL UNIQUE COLLATE NOCASE,
            email         TEXT    NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT    NOT NULL,
            created_at    TEXT    NOT NULL,
            is_active     INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS token_blacklist (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            jti        TEXT    NOT NULL UNIQUE,
            user_id    INTEGER NOT NULL,
            expires_at TEXT    NOT NULL,
            revoked_at TEXT    NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
    """)
    conn.commit()
    conn.close()


# ══════════════════════════════════════════════════════════════
# USER OPERATIONS
# ══════════════════════════════════════════════════════════════

def register_user(username: str, email: str, password: str) -> dict:
    """
    Create a new user. Returns {'ok': True, 'user_id': int} or
    {'ok': False, 'error': str}.
    """
    if len(password) < 8:
        return {"ok": False, "error": "Password must be at least 8 characters."}
    if len(username) < 3:
        return {"ok": False, "error": "Username must be at least 3 characters."}

    pw_hash = generate_password_hash(password, method="pbkdf2:sha256", salt_length=16)
    now     = datetime.now(timezone.utc).isoformat()

    conn = _conn()
    try:
        cur = conn.execute(
            "INSERT INTO users (username, email, password_hash, created_at) VALUES (?,?,?,?)",
            (username.strip(), email.strip().lower(), pw_hash, now),
        )
        conn.commit()
        return {"ok": True, "user_id": cur.lastrowid}
    except sqlite3.IntegrityError as e:
        msg = str(e)
        if "username" in msg:
            return {"ok": False, "error": "Username already taken."}
        if "email" in msg:
            return {"ok": False, "error": "Email already registered."}
        return {"ok": False, "error": "Registration failed."}
    finally:
        conn.close()


def authenticate_user(username: str, password: str) -> dict:
    """
    Verify credentials. Returns user row dict or None.
    Accepts username OR email in the username field.
    """
    conn = _conn()
    row = conn.execute(
        "SELECT * FROM users WHERE (username = ? OR email = ?) AND is_active = 1",
        (username.strip(), username.strip().lower()),
    ).fetchone()
    conn.close()

    if not row:
        return None
    if not check_password_hash(row["password_hash"], password):
        return None
    return dict(row)


def get_user_by_id(user_id: int) -> dict | None:
    conn = _conn()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ══════════════════════════════════════════════════════════════
# TOKEN OPERATIONS
# ══════════════════════════════════════════════════════════════

def _make_token(user_id: int, ttl: timedelta, token_type: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub":  str(user_id),
        "type": token_type,
        "jti":  secrets.token_hex(16),
        "iat":  now,
        "exp":  now + ttl,
    }
    return _jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(user_id: int) -> str:
    return _make_token(user_id, ACCESS_TTL, "access")


def create_refresh_token(user_id: int) -> str:
    return _make_token(user_id, REFRESH_TTL, "refresh")


def decode_token(token: str) -> dict | None:
    """Decode and validate a JWT. Returns payload or None if invalid/expired."""
    try:
        return _jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except _jwt.ExpiredSignatureError:
        return None
    except _jwt.InvalidTokenError:
        return None


def blacklist_token(token: str, user_id: int):
    """Add a token's JTI to the blacklist (logout / revoke)."""
    payload = decode_token(token)
    if not payload:
        return  # already invalid — nothing to do

    jti        = payload["jti"]
    expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc).isoformat()
    revoked_at = datetime.now(timezone.utc).isoformat()

    conn = _conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO token_blacklist (jti, user_id, expires_at, revoked_at) VALUES (?,?,?,?)",
            (jti, user_id, expires_at, revoked_at),
        )
        conn.commit()
    finally:
        conn.close()


def is_token_blacklisted(jti: str) -> bool:
    conn = _conn()
    row = conn.execute(
        "SELECT id FROM token_blacklist WHERE jti = ?", (jti,)
    ).fetchone()
    conn.close()
    return row is not None


def revoke_all_user_tokens(user_id: int):
    """Blacklist all active tokens for a user (force logout everywhere)."""
    # We can't enumerate issued JWTs, so we mark a per-user revocation timestamp.
    # All tokens issued before this timestamp are considered invalid.
    # Implemented via a dedicated column — added lazily here.
    conn = _conn()
    now = datetime.now(timezone.utc).isoformat()
    try:
        conn.execute("ALTER TABLE users ADD COLUMN revoked_before TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists
    conn.execute(
        "UPDATE users SET revoked_before = ? WHERE id = ?", (now, user_id)
    )
    conn.commit()
    conn.close()


def is_token_valid_for_user(payload: dict) -> bool:
    """Check that the token was issued AFTER any global revocation."""
    user = get_user_by_id(int(payload["sub"]))
    if not user:
        return False
    revoked_before = user.get("revoked_before")
    if revoked_before:
        iat = datetime.fromtimestamp(payload["iat"], tz=timezone.utc)
        rb  = datetime.fromisoformat(revoked_before)
        if iat < rb:
            return False
    return True


def purge_expired_blacklist():
    """Cleanup: remove expired blacklist entries (call periodically)."""
    conn = _conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("DELETE FROM token_blacklist WHERE expires_at < ?", (now,))
    conn.commit()
    conn.close()


# Auto-init on import
init_auth_db()
