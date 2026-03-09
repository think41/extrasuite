"""AES-256-GCM authenticated encryption for OAuth refresh tokens.

Output format: base64url(nonce || ciphertext || tag).

Each call to encrypt() generates a fresh random 12-byte nonce, so encrypting
the same plaintext twice produces different ciphertexts.  The tag (16 bytes)
ensures integrity: any corruption or wrong key raises ValueError on decrypt.
"""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class RefreshTokenEncryptor:
    """AES-256-GCM authenticated encryption for OAuth refresh tokens.

    Thread-safe: AESGCM is stateless; separate nonces are generated per call.
    """

    _NONCE_SIZE = 12  # 96-bit nonce — GCM recommendation

    def __init__(self, hex_key: str) -> None:
        """Initialise with a 32-byte hex-encoded key.

        Args:
            hex_key: 64-character hex string (32 bytes when decoded).

        Raises:
            ValueError: If hex_key is not a valid 64-character hex string.
        """
        try:
            key_bytes = bytes.fromhex(hex_key)
        except ValueError as e:
            raise ValueError(
                f"OAUTH_TOKEN_ENCRYPTION_KEY must be a valid hex string: {e}"
            ) from e
        if len(key_bytes) != 32:
            raise ValueError(
                f"OAUTH_TOKEN_ENCRYPTION_KEY must be 32 bytes (64 hex chars), "
                f"got {len(key_bytes)} bytes"
            )
        self._aesgcm = AESGCM(key_bytes)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a string and return a base64url-encoded ciphertext.

        The output is safe to store in Firestore and log (it reveals nothing
        about the plaintext without the key).

        Returns:
            base64url-encoded bytes: nonce (12 B) || ciphertext || tag (16 B).
        """
        nonce = os.urandom(self._NONCE_SIZE)
        ciphertext_with_tag = self._aesgcm.encrypt(nonce, plaintext.encode(), None)
        return base64.urlsafe_b64encode(nonce + ciphertext_with_tag).decode()

    def decrypt(self, ciphertext_b64: str) -> str:
        """Decrypt a base64url-encoded ciphertext produced by encrypt().

        Args:
            ciphertext_b64: Value previously returned by encrypt().

        Returns:
            Decrypted plaintext string.

        Raises:
            ValueError: On invalid base64url, short ciphertext, or
                authentication failure (wrong key, corrupted data).
        """
        # urlsafe_b64decode tolerates missing padding, but add "==" just in case
        try:
            combined = base64.urlsafe_b64decode(ciphertext_b64 + "==")
        except Exception as e:
            raise ValueError(f"Invalid base64url encoding: {e}") from e

        if len(combined) <= self._NONCE_SIZE:
            raise ValueError("Ciphertext too short to contain a nonce")

        nonce = combined[: self._NONCE_SIZE]
        ciphertext_with_tag = combined[self._NONCE_SIZE :]

        try:
            return self._aesgcm.decrypt(nonce, ciphertext_with_tag, None).decode()
        except Exception as e:
            raise ValueError(
                f"Decryption failed (wrong key or corrupted data): {e}"
            ) from e
