"""Testy dla api/auth.py — JWT autentykacja i hashowanie hasel.

Pokrywa:
- hash_password() / verify_password() — bcrypt hashing
- create_access_token() / verify_token() — JWT create + verify
- Token expiry — wygasly token zwraca 401
- Token payload — 'sub' claim
- Edge cases: pusty token, zly algorytm, zmodyfikowany token
"""

import os
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
from fastapi import HTTPException

# Set required env vars BEFORE any src.config import.
# Settings() is instantiated at module level in config.py.
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-minimum-32-chars-for-validator-check!!")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")

from src.api.auth import (  # noqa: E402
    create_access_token,
    hash_password,
    verify_password,
    verify_token,
)
from src.config import settings  # noqa: E402


# -- hash_password / verify_password ----------------------------------------


class TestPasswordHashing:
    """Bcrypt hashowanie hasel."""

    def test_hash_returns_string(self):
        h = hash_password("secret123")
        assert isinstance(h, str)

    def test_hash_starts_with_bcrypt_prefix(self):
        h = hash_password("secret123")
        assert h.startswith("$2b$")

    def test_hash_differs_from_plain(self):
        h = hash_password("secret123")
        assert h != "secret123"

    def test_same_password_different_hashes(self):
        """Bcrypt uses random salt — same password produces different hashes."""
        h1 = hash_password("secret123")
        h2 = hash_password("secret123")
        assert h1 != h2

    def test_verify_correct_password(self):
        h = hash_password("mypassword")
        assert verify_password("mypassword", h) is True

    def test_verify_wrong_password(self):
        h = hash_password("mypassword")
        assert verify_password("wrongpassword", h) is False

    def test_verify_empty_password(self):
        h = hash_password("")
        assert verify_password("", h) is True
        assert verify_password("notempty", h) is False

    def test_unicode_password(self):
        h = hash_password("zażółć gęślą jaźń")
        assert verify_password("zażółć gęślą jaźń", h) is True
        assert verify_password("zażółć", h) is False

    def test_long_password_raises(self):
        """bcrypt 5.x rejects passwords > 72 bytes (no auto-truncation)."""
        pw = "a" * 100
        with pytest.raises(ValueError, match="72 bytes"):
            hash_password(pw)

    def test_max_length_password(self):
        """72-byte password is the bcrypt maximum."""
        pw = "a" * 72
        h = hash_password(pw)
        assert verify_password(pw, h) is True


# -- create_access_token / verify_token --------------------------------------


class TestJwtTokens:
    """JWT tworzenie i weryfikacja tokenow."""

    def test_create_returns_string(self):
        token = create_access_token({"sub": "user@example.com"})
        assert isinstance(token, str)

    def test_create_and_verify_roundtrip(self):
        token = create_access_token({"sub": "user@example.com"})
        payload = verify_token(token)
        assert payload["sub"] == "user@example.com"

    def test_payload_contains_exp(self):
        token = create_access_token({"sub": "test"})
        payload = verify_token(token)
        assert "exp" in payload

    def test_custom_claims_preserved(self):
        token = create_access_token({"sub": "user", "role": "admin"})
        payload = verify_token(token)
        assert payload["role"] == "admin"

    def test_does_not_mutate_input(self):
        data = {"sub": "user@example.com"}
        create_access_token(data)
        assert "exp" not in data

    def test_expired_token_raises_401(self):
        """Manually create expired token."""
        payload = {
            "sub": "user@example.com",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        }
        expired_token = pyjwt.encode(
            payload,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        with pytest.raises(HTTPException) as exc_info:
            verify_token(expired_token)
        assert exc_info.value.status_code == 401

    def test_invalid_token_raises_401(self):
        with pytest.raises(HTTPException) as exc_info:
            verify_token("not.a.valid.token")
        assert exc_info.value.status_code == 401

    def test_empty_token_raises_401(self):
        with pytest.raises(HTTPException) as exc_info:
            verify_token("")
        assert exc_info.value.status_code == 401

    def test_wrong_secret_raises_401(self):
        """Token signed with different secret."""
        token = pyjwt.encode(
            {"sub": "user", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
            "different-secret-that-is-at-least-32-characters-long",
            algorithm="HS256",
        )
        with pytest.raises(HTTPException) as exc_info:
            verify_token(token)
        assert exc_info.value.status_code == 401

    def test_tampered_token_raises_401(self):
        """Modify token payload after signing."""
        token = create_access_token({"sub": "user"})
        parts = token.split(".")
        payload_part = list(parts[1])
        payload_part[0] = "X" if payload_part[0] != "X" else "Y"
        parts[1] = "".join(payload_part)
        tampered = ".".join(parts)
        with pytest.raises(HTTPException) as exc_info:
            verify_token(tampered)
        assert exc_info.value.status_code == 401

    def test_verify_returns_full_payload(self):
        token = create_access_token({"sub": "admin@example.com", "role": "admin"})
        payload = verify_token(token)
        assert "sub" in payload
        assert "exp" in payload
        assert "role" in payload

    def test_401_detail_message(self):
        with pytest.raises(HTTPException) as exc_info:
            verify_token("bad-token")
        assert "token" in exc_info.value.detail.lower()

    def test_401_www_authenticate_header(self):
        with pytest.raises(HTTPException) as exc_info:
            verify_token("bad-token")
        assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}
