"""Authentication and administrator authorization for the Streamlit app."""

from __future__ import annotations

import os
from dataclasses import dataclass

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError


@dataclass(frozen=True)
class Administrator:
    email: str
    name: str
    role: str = "Administrator"


ADMIN_NAMES = (
    "Tracy Wambui Mburu",
    "Stanley Gathekia",
)


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


def current_user_email() -> str:
    """Return the normalized email from Streamlit's authenticated OIDC user."""
    return normalize_email(st.user.get("email", ""))
