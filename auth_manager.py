import base64
import io
import os
import secrets
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
import pyotp
import qrcode
import qrcode.image.svg
from werkzeug.security import check_password_hash, generate_password_hash


AUTH_DB_PATH = Path(os.getenv("AUTH_DB_PATH", Path(__file__).with_name("auth.db")))
JWT_LIFETIME_HOURS = int(os.getenv("JWT_LIFETIME_HOURS", "8"))


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(AUTH_DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _utcnow() -> datetime:
    return datetime.now(UTC)


def initialize_auth_storage() -> None:
    AUTH_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(_connect()) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                totp_secret TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS app_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        connection.commit()

    _get_or_create_config("jwt_secret", secrets.token_urlsafe(64))


def _get_or_create_config(key: str, default_value: str) -> str:
    with closing(_connect()) as connection:
        row = connection.execute(
            "SELECT value FROM app_config WHERE key = ?",
            (key,),
        ).fetchone()
        if row:
            return str(row["value"])

        connection.execute(
            "INSERT OR IGNORE INTO app_config (key, value) VALUES (?, ?)",
            (key, default_value),
        )
        connection.commit()
        row = connection.execute(
            "SELECT value FROM app_config WHERE key = ?",
            (key,),
        ).fetchone()
        return str(row["value"]) if row else default_value


def has_users() -> bool:
    with closing(_connect()) as connection:
        row = connection.execute("SELECT 1 FROM users LIMIT 1").fetchone()
        return row is not None


def create_initial_user(username: str, password: str) -> dict:
    normalized_username = username.strip()
    if not normalized_username:
        raise ValueError("Username is required")
    if len(normalized_username) < 3:
        raise ValueError("Username must be at least 3 characters long")
    if len(password) < 12:
        raise ValueError("Password must be at least 12 characters long")
    if has_users():
        raise RuntimeError("Initial setup has already been completed")

    totp_secret = pyotp.random_base32()
    password_hash = generate_password_hash(password, method="scrypt")
    created_at = _utcnow().isoformat()

    with closing(_connect()) as connection:
        connection.execute(
            "INSERT INTO users (username, password_hash, totp_secret, created_at) VALUES (?, ?, ?, ?)",
            (normalized_username, password_hash, totp_secret, created_at),
        )
        connection.commit()

    return build_totp_setup_payload(normalized_username, totp_secret)


def build_totp_setup_payload(username: str, totp_secret: str) -> dict:
    issuer = os.getenv("TOTP_ISSUER", "CSCM Tool")
    uri = pyotp.TOTP(totp_secret).provisioning_uri(name=username, issuer_name=issuer)
    image = qrcode.make(uri, image_factory=qrcode.image.svg.SvgImage)
    buffer = io.BytesIO()
    image.save(buffer)
    svg_bytes = buffer.getvalue()
    qr_code_data_uri = "data:image/svg+xml;base64," + base64.b64encode(svg_bytes).decode("ascii")
    return {
        "totp_secret": totp_secret,
        "totp_uri": uri,
        "qr_code_data_uri": qr_code_data_uri,
    }


def authenticate_user(username: str, password: str, otp_code: str) -> dict | None:
    normalized_username = username.strip()
    with closing(_connect()) as connection:
        row = connection.execute(
            "SELECT id, username, password_hash, totp_secret FROM users WHERE username = ?",
            (normalized_username,),
        ).fetchone()

    if row is None:
        return None
    if not check_password_hash(str(row["password_hash"]), password):
        return None

    totp = pyotp.TOTP(str(row["totp_secret"]))
    if not totp.verify(otp_code.strip(), valid_window=1):
        return None

    return {
        "id": int(row["id"]),
        "username": str(row["username"]),
    }


def issue_jwt(user_id: int, username: str) -> tuple[str, int]:
    expires_at = _utcnow() + timedelta(hours=JWT_LIFETIME_HOURS)
    payload = {
        "sub": str(user_id),
        "username": username,
        "iat": int(_utcnow().timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(payload, _get_or_create_config("jwt_secret", secrets.token_urlsafe(64)), algorithm="HS256")
    return token, int(expires_at.timestamp())


def verify_jwt(token: str) -> dict | None:
    try:
        payload = jwt.decode(
            token,
            _get_or_create_config("jwt_secret", secrets.token_urlsafe(64)),
            algorithms=["HS256"],
        )
    except jwt.PyJWTError:
        return None

    return {
        "id": int(payload["sub"]),
        "username": str(payload["username"]),
    }