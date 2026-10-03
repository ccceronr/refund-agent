"""Staff password hashing: argon2id with the library's RFC 9106 defaults (OWASP A04, A07)."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_HASHER = PasswordHasher()
# Checked when the username doesn't exist, so a wrong username takes as long as a wrong
# password and the response time doesn't reveal which usernames exist (OWASP A07).
_DECOY_HASH = _HASHER.hash("decoy password that matches no account")


def hash_password(password: str) -> str:
    return _HASHER.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """False for a wrong password and for a missing hash (an account that can't sign in)."""
    try:
        _HASHER.verify(password_hash or _DECOY_HASH, password)
    except (VerificationError, InvalidHashError):
        return False
    return password_hash is not None
