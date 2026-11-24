"""Password hashing and opaque token helpers."""

import hashlib
import hmac
import secrets

from pwdlib import PasswordHash

# pwdlib's recommended configuration currently uses Argon2id.
password_hasher = PasswordHash.recommended()

# A hash of a random throwaway value. Login verifies against it when the email
# does not exist so response timing does not reveal which emails are registered.
_DUMMY_PASSWORD_HASH = password_hasher.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    """Return an Argon2id hash suitable for storage in users.password_hash."""
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Check a plaintext password against a stored password hash."""
    try:
        return password_hasher.verify(password, password_hash)
    except Exception:
        # A malformed or unknown stored hash must fail closed.
        return False


def verify_dummy_password(password: str) -> None:
    """Spend roughly the same time as a real password check."""
    try:
        password_hasher.verify(password, _DUMMY_PASSWORD_HASH)
    except Exception:
        pass


def generate_session_token() -> str:
    """Return a 256-bit, URL-safe session token."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """Hash a session token for storage.

    SHA-256 is appropriate here because the token is a high-entropy random
    value, not a human-chosen password.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_csrf_token() -> str:
    """Return a random token for the double-submit CSRF cookie."""
    return secrets.token_urlsafe(32)


def tokens_match(left: str, right: str) -> bool:
    """Compare secrets without leaking their contents through timing."""
    return hmac.compare_digest(left, right)
