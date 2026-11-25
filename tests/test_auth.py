from __future__ import annotations

from types import SimpleNamespace

import pytest

import fishops.auth as auth


def _response(
    email: str = "mburutracy81@gmail.com",
    email_confirmed_at: str | None = "2026-01-01T00:00:00Z",
):
    return SimpleNamespace(
        session=SimpleNamespace(
            access_token="access-token",
            refresh_token="refresh-token",
            expires_at=2_000_000_000,
            expires_in=3600,
        ),
        user=SimpleNamespace(email=email, email_confirmed_at=email_confirmed_at),
    )


class FakeSupabaseAuth:
    def __init__(self, response):
        self.response = response
        self.sign_in_credentials = None
        self.refresh_token = None
        self.sign_out_options = None
        self.session_tokens = None
        self.recovery_email = None

    def sign_in_with_password(self, credentials):
        self.sign_in_credentials = credentials
        return self.response

    def reset_password_for_email(self, email):
        self.recovery_email = email

    def refresh_session(self, refresh_token):
        self.refresh_token = refresh_token
        return self.response

    def set_session(self, access_token, refresh_token):
        self.session_tokens = (access_token, refresh_token)

    def sign_out(self, options):
        self.sign_out_options = options


class FakeSupabaseClient:
    def __init__(self, response):
        self.auth = FakeSupabaseAuth(response)


def _configure_admin(monkeypatch):
    monkeypatch.setenv("FISHOPS_ADMIN_EMAIL_1", "mburutracy81@gmail.com")
    monkeypatch.setenv("FISHOPS_ADMIN_EMAIL_2", "njorogestan12@gmail.com")
    monkeypatch.setenv("SUPABASE_URL", "https://fishops.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "publishable-key")


def test_sign_in_uses_supabase_and_returns_per_user_session(monkeypatch):
    _configure_admin(monkeypatch)
    client = FakeSupabaseClient(_response())
    create_client_calls = []
    monkeypatch.setattr(
        auth,
        "create_client",
        lambda url, key: create_client_calls.append((url, key)) or client,
    )

    session = auth.sign_in_with_password(" MBURUTRACY81@GMAIL.COM ", "individual-password")

    assert create_client_calls == [
        ("https://fishops.supabase.co", "publishable-key")
    ]
    assert client.auth.sign_in_credentials == {
        "email": "mburutracy81@gmail.com",
        "password": "individual-password",
    }
    assert session.email == "mburutracy81@gmail.com"
    assert session.refresh_token == "refresh-token"
    assert "individual-password" not in repr(session)


def test_unlisted_email_is_rejected_before_supabase_auth(monkeypatch):
    _configure_admin(monkeypatch)
    monkeypatch.setattr(
        auth,
        "create_client",
        lambda *_: pytest.fail("Supabase should not be called for an unlisted email"),
    )

    with pytest.raises(auth.UnauthorizedAdministratorError):
        auth.sign_in_with_password("outsider@example.com", "password")


def test_password_recovery_uses_implicit_flow_for_authorized_email(monkeypatch):
    _configure_admin(monkeypatch)
    client = FakeSupabaseClient(_response())
    create_client_calls = []
    monkeypatch.setattr(
        auth,
        "create_client",
        lambda url, key, options: (
            create_client_calls.append((url, key, options.flow_type)) or client
        ),
    )

    auth.send_password_recovery_email(" MBURUTRACY81@GMAIL.COM ")

    assert create_client_calls == [
        ("https://fishops.supabase.co", "publishable-key", "implicit")
    ]
    assert client.auth.recovery_email == "mburutracy81@gmail.com"


def test_password_recovery_does_not_send_for_unlisted_email(monkeypatch):
    _configure_admin(monkeypatch)
    monkeypatch.setattr(
        auth,
        "create_client",
        lambda *_args, **_kwargs: pytest.fail(
            "Supabase should not be called for an unlisted email"
        ),
    )

    auth.send_password_recovery_email("outsider@example.com")


def test_unconfirmed_account_is_signed_out_and_rejected(monkeypatch):
    _configure_admin(monkeypatch)
    client = FakeSupabaseClient(_response(email_confirmed_at=None))
    monkeypatch.setattr(auth, "create_client", lambda *_: client)

    with pytest.raises(auth.UnconfirmedEmailError):
        auth.sign_in_with_password("mburutracy81@gmail.com", "individual-password")

    assert client.auth.sign_out_options == {"scope": "local"}


def test_refresh_and_sign_out_are_scoped_to_current_session(monkeypatch):
    _configure_admin(monkeypatch)
    client = FakeSupabaseClient(_response())
    monkeypatch.setattr(auth, "create_client", lambda *_: client)

    session = auth.refresh_authenticated_session("refresh-token")
    auth.sign_out_session(session)

    assert client.auth.refresh_token == "refresh-token"
    assert client.auth.session_tokens == ("access-token", "refresh-token")
    assert client.auth.sign_out_options == {"scope": "local"}


def test_invitation_browser_config_contains_only_public_settings(monkeypatch):
    _configure_admin(monkeypatch)
    url, key, emails = auth.get_invitation_browser_config()

    assert url == "https://fishops.supabase.co"
    assert key == "publishable-key"
    assert emails == ("mburutracy81@gmail.com", "njorogestan12@gmail.com")
