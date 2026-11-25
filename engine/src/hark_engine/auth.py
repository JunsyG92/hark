"""API token management.

The master token is generated on first launch and stored in the OS credential
manager (Windows Credential Manager, macOS Keychain, Linux Secret Service) via
``keyring``. If no secure backend is available (e.g. headless Linux without a
Secret Service), we fall back to a 0600 file in the data dir and log a warning.
"""

from __future__ import annotations

import hmac
import logging
import os
import secrets
from enum import StrEnum
from pathlib import Path

import keyring
import keyring.errors
from keyring.backends import fail

log = logging.getLogger(__name__)

KEYRING_SERVICE = "hark"
KEYRING_USER = "api-token"
TOKEN_BYTES = 32


class Scope(StrEnum):
    """Permission scopes. ``ui`` is the desktop app (full control)."""

    READ = "read"
    PROPOSE = "propose"
    UI = "ui"


def generate_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def _keyring_usable() -> bool:
    backend = keyring.get_keyring()
    return not isinstance(backend, fail.Keyring) and backend.priority > 0


def load_or_create_master_token(data_dir: Path) -> str:
    """Return the master token, creating and persisting it on first launch."""
    env_token = os.environ.get("HARK_TOKEN")
    if env_token:
        return env_token

    if _keyring_usable():
        try:
            existing = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
            if existing:
                return existing
            token = generate_token()
            keyring.set_password(KEYRING_SERVICE, KEYRING_USER, token)
            return token
        except keyring.errors.KeyringError as exc:  # pragma: no cover - OS specific
            log.warning("OS credential store unavailable (%s); using file fallback", exc)

    log.warning("No OS credential store available; token stored in a 0600 file")
    token_file = data_dir / ".token"
    if token_file.exists():
        return token_file.read_text(encoding="utf-8").strip()
    token = generate_token()
    token_file.write_text(token, encoding="utf-8")
    token_file.chmod(0o600)
    return token


def tokens_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
