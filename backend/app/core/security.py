"""Password hashing and password policy utilities."""

from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from pwdlib.hashers.argon2 import Argon2Hasher

MIN_PASSWORD_LENGTH = 15

# These are pwdlib 0.3.1's recommended Argon2id parameters, specified explicitly
# so a library upgrade cannot silently change the resource cost of new hashes.
_password_hasher = PasswordHash(
    hashers=[Argon2Hasher(time_cost=3, memory_cost=65536, parallelism=4)]
)


def validate_password(password: str) -> None:
    """Raise ValueError unless the password contains at least 15 characters.

    Passwords are counted as Unicode code points and are not trimmed or
    normalized. No composition rules or maximum length are imposed.
    """

    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError("Password must be at least 15 characters long")


def hash_password(password: str) -> str:
    """Return a salted Argon2id encoded hash for a valid password."""

    validate_password(password)
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its encoded hash, returning False if invalid."""

    if not isinstance(password, str) or not isinstance(password_hash, str):
        return False

    try:
        return _password_hasher.verify(password, password_hash)
    except UnknownHashError:
        return False
