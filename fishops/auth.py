"""Auth0 identity handling and administrator authorization."""

import os
from dataclasses import dataclass

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError


ADMIN_NAMES = (
    "Tracy Wambui Mburu",
    "Stanley Gathekia",
)


@dataclass(frozen=True)
class Administrator:
    email: str
    name: str
    role: str = "Administrator"


def normalize_email(email: str | None) -> str:
    """Normalize an email for exact allowlist matching."""
    return (email or "").strip().lower()


def _configured_admin_emails() -> tuple[str, str]:
    try:
        admins = st.secrets.get("admins", {})
    except StreamlitSecretNotFoundError:
        admins = {}

    return (
        normalize_email(os.getenv("FISHOPS_ADMIN_EMAIL_1") or admins.get("email_1")),
        normalize_email(os.getenv("FISHOPS_ADMIN_EMAIL_2") or admins.get("email_2")),
    )


def get_authorized_administrator(email: str | None) -> Administrator | None:
    """Return the configured administrator for an exact normalized email match."""
    normalized_email = normalize_email(email)
    if not normalized_email:
        return None

    for configured_email, name in zip(_configured_admin_emails(), ADMIN_NAMES):
        if configured_email and configured_email == normalized_email:
            return Administrator(email=normalized_email, name=name)
    return None


def get_authenticated_administrator(
    email: object, email_verified: object
) -> Administrator | None:
    """Authorize only an allowlisted account with a verified Auth0 email."""
    if not isinstance(email, str) or email_verified is not True:
        return None
    return get_authorized_administrator(email)


def is_auth0_configured() -> bool:
    """Check that Streamlit has the shared and Auth0-specific OIDC settings."""
    try:
        settings = st.secrets.get("auth", {})
    except StreamlitSecretNotFoundError:
        return False

    provider = settings.get("auth0", {})
    shared_keys = ("redirect_uri", "cookie_secret")
    provider_keys = ("client_id", "client_secret", "server_metadata_url")
    return all(settings.get(key) for key in shared_keys) and all(
        provider.get(key) for key in provider_keys
    )
