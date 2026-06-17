"""Cookie file encryption for Amazon Photos MCP.

Uses AES-256-GCM with a key derived from machine identity.
Plaintext fallback for backward compatibility — existing unencrypted
cookie files continue to work and are encrypted on next write.
"""

from __future__ import annotations

import hashlib
import json
import platform
import secrets
import sys
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class DecryptionError(Exception):
    """Raised when the cookie file exists but cannot be decrypted."""

    pass


_MACHINE_KEY_CACHE: bytes | None = None


# Per-project salt — does not need to be secret, but ensures keys differ
# across applications even if machine attributes are identical.
_KEY_SALT = b"amazon-photos-mcp:cookie-vault:v1"

# PBKDF2 iteration count — high enough to slow brute-force, low enough
# to not noticeably delay startup (~50ms on modern hardware).
_KEY_ITERATIONS = 200_000


def _machine_key() -> bytes:
    """Derive a 32-byte key from machine-specific attributes via PBKDF2.

    Uses HMAC-SHA256 with a per-project salt and 200k iterations.
    This is NOT a substitute for a user-provided secret — it protects
    against casual inspection but an attacker with local access who can
    read machine identity attributes can recompute the key.

    Cached at module level — derived once per process lifetime.
    """
    global _MACHINE_KEY_CACHE
    if _MACHINE_KEY_CACHE is not None:
        return _MACHINE_KEY_CACHE

    parts = [
        platform.node() or "unknown-host",
        platform.machine() or "unknown-arch",
        str(Path.home()),
    ]
    if sys.platform == "win32":
        try:
            import subprocess

            result = subprocess.run(
                ["powershell", "-Command", "(Get-CimInstance Win32_ComputerSystemProduct).UUID"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            uuid_val = result.stdout.strip()
            if uuid_val:
                parts.append(uuid_val)
        except Exception:
            pass
    else:
        for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            try:
                val = Path(p).read_text().strip()
                if val:
                    parts.append(val)
                    break
            except Exception:
                pass

    seed = "|".join(parts).encode("utf-8")
    _MACHINE_KEY_CACHE = hashlib.pbkdf2_hmac("sha256", seed, _KEY_SALT, _KEY_ITERATIONS, dklen=32)
    return _MACHINE_KEY_CACHE


def _encrypt(plaintext: bytes) -> bytes:
    """Encrypt plaintext. Returns nonce (12 bytes) + ciphertext + tag."""
    key = _machine_key()
    aesgcm = AESGCM(key)
    nonce = secrets.token_bytes(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return nonce + ciphertext


def _decrypt(data: bytes) -> bytes:
    """Decrypt data produced by _encrypt."""
    key = _machine_key()
    nonce = data[:12]
    ciphertext = data[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)


def load_encrypted_cookies(path: Path) -> dict[str, Any] | None:
    """Load cookies from a JSON file. Handles both plaintext and encrypted formats.

    Returns None if the file doesn't exist or can't be read.
    Returns the cookie dict on success.
    """
    if not path.exists():
        return None

    try:
        raw = path.read_bytes()

        # Try encrypted first (has "AMCP" magic header)
        if raw[:4] == b"AMCP":
            decrypted = _decrypt(raw[4:])
            return json.loads(decrypted)
        else:
            # Plaintext backward compatibility — reuse the bytes we already read
            return json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, ValueError, OSError):
        return None
    except InvalidTag as e:
        # _decrypt raises InvalidTag on corrupted or tampered payloads
        raise DecryptionError("Failed to decrypt cookie file. The encryption key may have changed.") from e


def save_encrypted_cookies(path: Path, cookies: dict[str, Any]) -> None:
    """Save cookies as encrypted JSON. Creates parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    plaintext = json.dumps(cookies, indent=2).encode("utf-8")
    encrypted = _encrypt(plaintext)
    path.write_bytes(b"AMCP" + encrypted)
    # Restrictive permissions on Unix
    if sys.platform != "win32":
        path.chmod(0o600)
