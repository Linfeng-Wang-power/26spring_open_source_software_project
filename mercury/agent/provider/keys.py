"""Cross-platform API key resolution.

Order of resolution:
1. Explicit override (e.g. passed in by tests).
2. OS keyring (macOS Keychain, Windows Credential Locker, Linux SecretService).
3. Environment variable fallback.

Keys are NEVER persisted to SQLite or logged.
"""

from __future__ import annotations

import os

KEYRING_SERVICE = "mercury-pyqt"


def resolve_api_key(
    *,
    profile: str = "default",
    env_var: str = "OPENAI_API_KEY",
    override: str | None = None,
) -> str | None:
    """Look up an API key for *profile* without ever logging it.

    Returns None when no key is configured anywhere.
    """
    if override is not None:
        return override or None

    try:
        import keyring  # type: ignore
    except ImportError:
        keyring = None  # noqa: N806

    if keyring is not None:
        try:
            value = keyring.get_password(KEYRING_SERVICE, profile)
        except Exception:
            # Keyring backend can fail (no daemon on Linux CI, locked Keychain, etc.)
            value = None
        if value:
            return value

    env_value = os.environ.get(env_var)
    if env_value:
        return env_value
    return None


def store_api_key(value: str, *, profile: str = "default") -> bool:
    """Persist an API key in the OS keyring. Returns False when unavailable."""
    try:
        import keyring  # type: ignore
    except ImportError:
        return False
    try:
        keyring.set_password(KEYRING_SERVICE, profile, value)
        return True
    except Exception:
        return False
