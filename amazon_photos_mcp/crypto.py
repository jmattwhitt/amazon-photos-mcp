"""Cookie file encryption for Amazon Photos MCP."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
from pathlib import Path
from typing import Any


def _machine_key() -> bytes:
    """Derive a 32-byte key from machine-specific attributes."""
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
            parts.append(result.stdout.strip())
        except Exception:
            pass
    else:
        for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            try:
                parts.append(Path(p).read_text().strip())
                break
            except Exception:
                pass

    seed = "|".join(parts).encode("utf-8")
    return hashlib.sha256(seed).digest()


def _encrypt(plaintext: bytes) -> bytes:
    """Encrypt plaintext. Returns nonce (12 bytes) + ciphertext + tag."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    import secrets

    key = _machine_key()
    aesgcm = AESGCM(key)
    nonce = secrets.token_bytes(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return nonce + ciphertext


def _decrypt(data: bytes) -> bytes:
    """Decrypt data produced by _encrypt."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = _machine_key()
    nonce = data[:12]
    ciphertext = data[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)


def load_encrypted_cookies(path: Path) -> dict[str, Any] | None:
    """Load cookies from a JSON file. Handles both plaintext and encrypted formats."""
    if not path.exists():
        return None

    try:
        raw = path.read_bytes()

        # Try encrypted first (has "AMCP" magic header)
        if raw[:4] == b"AMCP":
            decrypted = _decrypt(raw[4:])
            return json.loads(decrypted)
        else:
            # Plaintext backward compatibility
            return json.loads(path.read_text())
    except (json.JSONDecodeError, ValueError, OSError):
        return None


def save_encrypted_cookies(path: Path, cookies: dict[str, Any]) -> None:
    """Save cookies as encrypted JSON. Creates parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    plaintext = json.dumps(cookies, indent=2).encode("utf-8")
    encrypted = _encrypt(plaintext)
    path.write_bytes(b"AMCP" + encrypted)
    # Restrictive permissions on Unix
    if sys.platform != "win32":
        path.chmod(0o600)
