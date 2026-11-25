"""Supabase password authentication and administrator authorization."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError
from supabase import Client, create_client
from supabase.lib.client_options import SyncClientOptions
from supabase_auth.types import AuthResponse


ADMIN_NAMES = (
    "Tracy Wambui Mburu",
    "Stanley Gathekia",
)


@dataclass(frozen=True)
class Administrator:
    email: str
    name: str
    role: str = "Administrator"


@dataclass(frozen=True, repr=False)
class AuthenticatedSession:
    email: str
    access_token: str
    refresh_token: str
    expires_at: int


class SupabaseAuthConfigurationError(RuntimeError):
    """Raised when the public Supabase Auth settings are missing."""


class SupabaseAuthSessionError(RuntimeError):
    """Raised when Supabase returns an incomplete or unconfirmed session."""


class UnauthorizedAdministratorError(PermissionError):
    """Raised when an authenticated email is not on the administrator allowlist."""


class UnconfirmedEmailError(PermissionError):
    """Raised when the Supabase account email has not been confirmed."""


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


def _configured_supabase_auth_settings() -> tuple[str, str]:
    try:
        settings = st.secrets.get("supabase", {})
    except StreamlitSecretNotFoundError:
        settings = {}

    url = os.getenv("SUPABASE_URL") or settings.get("url")
    publishable_key = (
        os.getenv("SUPABASE_PUBLISHABLE_KEY") or settings.get("publishable_key")
    )
    if (
        not isinstance(url, str)
        or not url.startswith("https://")
        or not isinstance(publishable_key, str)
        or not publishable_key
    ):
        raise SupabaseAuthConfigurationError(
            "Supabase Auth URL and publishable key are not configured."
        )

    return url, publishable_key


def get_invitation_browser_config() -> tuple[str, str, tuple[str, ...]]:
    """Return only public client settings needed to complete email invitations."""
    url, publishable_key = _configured_supabase_auth_settings()
    admin_emails = tuple(email for email in _configured_admin_emails() if email)
    return url, publishable_key, admin_emails


def _create_supabase_auth_client() -> Client:
    url, publishable_key = _configured_supabase_auth_settings()
    return create_client(url, publishable_key)


def _session_from_response(response: AuthResponse) -> AuthenticatedSession:
    session = response.session
    user = response.user
    if session is None or user is None:
        raise SupabaseAuthSessionError("Supabase did not return an authenticated session.")
    if user.email_confirmed_at is None:
        raise UnconfirmedEmailError("The Supabase account email is not confirmed.")

    email = normalize_email(user.email)
    if not email:
        raise SupabaseAuthSessionError("Supabase did not return an account email.")

    return AuthenticatedSession(
        email=email,
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        expires_at=session.expires_at or int(time.time()) + session.expires_in,
    )


def sign_in_with_password(email: str, password: str) -> AuthenticatedSession:
    """Authenticate an existing, allowlisted Supabase user without storing its password."""
    normalized_email = normalize_email(email)
    if not password or not normalized_email:
        raise ValueError("Both email and password are required.")

    if get_authorized_administrator(normalized_email) is None:
        raise UnauthorizedAdministratorError("This email is not an authorized administrator.")

    client = _create_supabase_auth_client()
    response = client.auth.sign_in_with_password(
        {"email": normalized_email, "password": password}
    )
    if response.user is not None and response.user.email_confirmed_at is None:
        client.auth.sign_out({"scope": "local"})
        raise UnconfirmedEmailError("The Supabase account email is not confirmed.")

    authenticated_session = _session_from_response(response)
    if (
        authenticated_session.email != normalized_email
        or get_authorized_administrator(authenticated_session.email) is None
    ):
        client.auth.sign_out({"scope": "local"})
        raise UnauthorizedAdministratorError(
            "This email is not an authorized administrator."
        )
    return authenticated_session


def send_password_recovery_email(email: str) -> None:
    """Send an implicit-flow password recovery link to an authorized administrator."""
    normalized_email = normalize_email(email)
    if not normalized_email:
        raise ValueError("An email address is required.")

    if get_authorized_administrator(normalized_email) is None:
        return

    url, publishable_key = _configured_supabase_auth_settings()
    client = create_client(
        url,
        publishable_key,
        options=SyncClientOptions(flow_type="implicit"),
    )
    client.auth.reset_password_for_email(normalized_email)


def refresh_authenticated_session(refresh_token: str) -> AuthenticatedSession:
    """Refresh one user's session using that user's refresh token."""
    response = _create_supabase_auth_client().auth.refresh_session(refresh_token)
    return _session_from_response(response)


def sign_out_session(authenticated_session: AuthenticatedSession) -> None:
    """Sign out only the current Supabase session."""
    client = _create_supabase_auth_client()
    client.auth.set_session(
        authenticated_session.access_token,
        authenticated_session.refresh_token,
    )
    client.auth.sign_out({"scope": "local"})
