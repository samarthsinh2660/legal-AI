"""Password hashing.

Argon2id, not bcrypt and emphatically not a bare hash. The threat is an
attacker who has the database -- a stolen dump, a backup, a misconfigured
port -- and wants the plaintext. Against that, speed is the enemy: a fast
hash lets them try billions of candidates a second on a GPU.

Two properties are load-bearing and each has a test below. The same password
must hash differently every time, or identical hashes reveal which users
share a password. And verification must be the only way to compare, because
a caller that reaches for `==` on two hashes has quietly reintroduced a
timing leak.
"""

import pytest

from api.utils.passwords import (
    hash_password,
    needs_rehash,
    verify_password,
)


def test_a_password_verifies_against_its_own_hash():
    secret = "correct horse battery staple"
    assert verify_password(secret, hash_password(secret))


def test_a_wrong_password_does_not_verify():
    assert not verify_password("wrong", hash_password("right"))


def test_the_hash_is_not_the_password():
    """The obvious failure, worth a test because it is catastrophic."""
    secret = "hunter2"
    assert secret not in hash_password(secret)


def test_the_same_password_hashes_differently_each_time():
    """Salting. Without it, two users with the same password get the same
    hash, and a dump tells an attacker which accounts to attack together."""
    assert hash_password("same") != hash_password("same")


def test_an_empty_password_is_refused():
    """Not a hashing question -- a hash of "" is a valid hash, and would
    make an account with no password look exactly like a real one."""
    with pytest.raises(ValueError):
        hash_password("")


def test_whitespace_only_is_refused():
    with pytest.raises(ValueError):
        hash_password("    ")


def test_a_malformed_hash_verifies_false_rather_than_raising():
    """A corrupt or truncated row must fail the login, not crash the
    endpoint -- a 500 here tells an attacker they found something."""
    assert not verify_password("anything", "not-a-real-hash")
    assert not verify_password("anything", "")


def test_a_current_hash_does_not_need_rehashing():
    assert not needs_rehash(hash_password("whatever"))


def test_a_foreign_hash_is_reported_as_needing_rehash():
    """Parameters get raised over time. A login is the only moment the
    plaintext is in hand, so it is the only moment an upgrade is possible."""
    assert needs_rehash("not-argon2-at-all")


def test_unicode_survives_the_round_trip():
    secret = "पासवर्ड-🔐-ключ"
    assert verify_password(secret, hash_password(secret))


def test_a_long_password_is_not_silently_truncated():
    """bcrypt caps at 72 bytes and ignores the rest, so two different long
    passwords can share a hash. Argon2 does not, and this pins that."""
    base = "x" * 100
    assert not verify_password(base + "A", hash_password(base + "B"))
