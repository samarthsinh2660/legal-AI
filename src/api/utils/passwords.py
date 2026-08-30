"""Password hashing with Argon2id.

Argon2 rather than bcrypt: it is memory-hard, so a GPU loses most of its
advantage, and bcrypt silently truncates at 72 bytes, which lets two
different long passwords share a hash.

Cost parameters are the library defaults. Hashing is meant to be slow.

`verify_password` is the only comparison -- never `==` on two hashes.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import (
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """An Argon2id hash of `password`, salted, safe to store.

    Refuses an empty password: hashing one succeeds, and the account it
    creates can be entered by anyone submitting an empty form.
    """
    if not password or not password.strip():
        raise ValueError("password must not be empty")
    return _hasher.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    """Whether `password` matches `stored_hash`.

    False for a malformed hash rather than raising: a corrupt row should
    fail the login, not return a 500 that tells an attacker they found
    something.
    """
    if not stored_hash:
        return False
    try:
        return _hasher.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    """Whether `stored_hash` used weaker parameters than current.

    A login is the only moment the plaintext is in hand, so the only moment
    an old hash can be upgraded.
    """
    try:
        return _hasher.check_needs_rehash(stored_hash)
    except (InvalidHashError, VerificationError):
        # Unreadable is not "current". Treating it as fine would keep a
        # broken row in place indefinitely.
        return True
