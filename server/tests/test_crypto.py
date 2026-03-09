"""Tests for RefreshTokenEncryptor (AES-256-GCM)."""

import base64
import secrets

import pytest

from extrasuite.server.crypto import RefreshTokenEncryptor


def _make_key() -> str:
    """Generate a random valid 32-byte hex key."""
    return secrets.token_hex(32)


class TestRefreshTokenEncryptor:
    def test_round_trip(self):
        enc = RefreshTokenEncryptor(_make_key())
        plaintext = "1//04xSomeOAuthRefreshToken-XYZ_abc123"
        ciphertext = enc.encrypt(plaintext)
        assert enc.decrypt(ciphertext) == plaintext

    def test_encrypt_produces_base64url(self):
        enc = RefreshTokenEncryptor(_make_key())
        ciphertext = enc.encrypt("hello")
        # Should be valid base64url — decode without error
        decoded = base64.urlsafe_b64decode(ciphertext + "==")
        # Nonce (12) + at least 1 byte plaintext + tag (16) = at least 29 bytes
        assert len(decoded) >= 29

    def test_each_encrypt_produces_different_ciphertext(self):
        enc = RefreshTokenEncryptor(_make_key())
        plaintext = "same token"
        ct1 = enc.encrypt(plaintext)
        ct2 = enc.encrypt(plaintext)
        assert ct1 != ct2, "Nonces must differ between encryptions"

    def test_wrong_key_raises_on_decrypt(self):
        enc1 = RefreshTokenEncryptor(_make_key())
        enc2 = RefreshTokenEncryptor(_make_key())
        ciphertext = enc1.encrypt("secret")
        with pytest.raises(ValueError, match=r"[Dd]ecryption failed"):
            enc2.decrypt(ciphertext)

    def test_corrupted_ciphertext_raises(self):
        enc = RefreshTokenEncryptor(_make_key())
        ciphertext = enc.encrypt("secret")
        # Flip a byte in the base64 representation
        corrupted = ciphertext[:-4] + "XXXX"
        with pytest.raises(ValueError):
            enc.decrypt(corrupted)

    def test_short_key_raises(self):
        short_key = secrets.token_hex(16)  # 16 bytes, not 32
        with pytest.raises(ValueError, match="32 bytes"):
            RefreshTokenEncryptor(short_key)

    def test_invalid_hex_raises(self):
        with pytest.raises(ValueError, match="valid hex"):
            RefreshTokenEncryptor("not-a-hex-string!!!")

    def test_empty_plaintext(self):
        enc = RefreshTokenEncryptor(_make_key())
        ct = enc.encrypt("")
        assert enc.decrypt(ct) == ""

    def test_long_plaintext(self):
        enc = RefreshTokenEncryptor(_make_key())
        long_text = "x" * 10_000
        ct = enc.encrypt(long_text)
        assert enc.decrypt(ct) == long_text

    def test_truncated_ciphertext_raises(self):
        enc = RefreshTokenEncryptor(_make_key())
        # Encode just 4 bytes (less than nonce size)
        tiny = base64.urlsafe_b64encode(b"\x00\x01\x02\x03").decode()
        with pytest.raises(ValueError, match="too short"):
            enc.decrypt(tiny)

    def test_invalid_base64_raises(self):
        enc = RefreshTokenEncryptor(_make_key())
        with pytest.raises(ValueError):
            enc.decrypt("not-valid-base64!!!")
