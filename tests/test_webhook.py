"""Unit tests for webhook HMAC signature validation."""
import hashlib
import hmac

import pytest

from app.routers.webhook import validate_signature


def _make_sig(secret: bytes, body: bytes) -> str:
    return "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()


class TestValidateSignature:
    def test_valid_signature(self):
        secret = b"test_secret"
        body = b'{"action": "opened"}'
        assert validate_signature(secret, body, _make_sig(secret, body)) is True

    def test_invalid_hex(self):
        assert validate_signature(b"secret", b"body", "sha256=deadbeef") is False

    def test_missing_signature(self):
        assert validate_signature(b"secret", b"body", "") is False

    def test_wrong_prefix(self):
        secret = b"test_secret"
        body = b"test"
        raw = hmac.new(secret, body, hashlib.sha256).hexdigest()
        assert validate_signature(secret, body, f"sha1={raw}") is False

    def test_tampered_body(self):
        secret = b"test_secret"
        body = b'{"action": "opened"}'
        sig = _make_sig(secret, body)
        assert validate_signature(secret, b'{"action": "closed"}', sig) is False

    def test_different_secret(self):
        body = b"payload"
        sig = _make_sig(b"correct_secret", body)
        assert validate_signature(b"wrong_secret", body, sig) is False

    def test_empty_secret_with_matching_sig(self):
        secret = b""
        body = b"data"
        assert validate_signature(secret, body, _make_sig(secret, body)) is True
