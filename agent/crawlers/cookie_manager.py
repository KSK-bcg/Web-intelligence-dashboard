# agent/crawlers/cookie_manager.py
"""
Manages LinkedIn session cookies using OS keyring.
Cookies are NEVER written to .env or logs.
"""
import json
import keyring
import logging

logger = logging.getLogger(__name__)

SERVICE_NAME = "web-intelligence-agent"
COOKIE_KEY = "linkedin-session-cookies"


def save_cookies(cookies: list) -> None:
    """Persist cookies to OS keyring (encrypted by OS)."""
    logger.info("Saving %d LinkedIn session cookies to keyring", len(cookies))
    keyring.set_password(SERVICE_NAME, COOKIE_KEY, json.dumps(cookies))


def load_cookies():
    """Load cookies from OS keyring. Returns None if not set."""
    raw = keyring.get_password(SERVICE_NAME, COOKIE_KEY)
    if not raw:
        return None
    return json.loads(raw)


def clear_cookies() -> None:
    """Remove stored cookies (e.g., after auth expiry)."""
    try:
        keyring.delete_password(SERVICE_NAME, COOKIE_KEY)
        logger.info("LinkedIn session cookies cleared from keyring")
    except Exception:
        pass  # Already cleared or not set
