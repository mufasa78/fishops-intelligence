import fishops.auth as auth


def _configure_admin(monkeypatch):
    monkeypatch.setenv("FISHOPS_ADMIN_EMAIL_1", "mburutracy81@gmail.com")
    monkeypatch.setenv("FISHOPS_ADMIN_EMAIL_2", "njorogestan12@gmail.com")


def test_authorizes_configured_email_case_insensitively(monkeypatch):
    _configure_admin(monkeypatch)

    administrator = auth.get_authorized_administrator(" MBURUTRACY81@GMAIL.COM ")

    assert administrator == auth.Administrator(
        email="mburutracy81@gmail.com",
        name="Tracy Wambui Mburu",
    )


def test_rejects_unlisted_email(monkeypatch):
    _configure_admin(monkeypatch)

    assert auth.get_authorized_administrator("outsider@example.com") is None


def test_auth0_user_requires_verified_allowlisted_email(monkeypatch):
    _configure_admin(monkeypatch)

    assert auth.get_authenticated_administrator(
        "MBURUTRACY81@GMAIL.COM", True
    ) == auth.Administrator(
        email="mburutracy81@gmail.com",
        name="Tracy Wambui Mburu",
    )
    assert auth.get_authenticated_administrator(
        "mburutracy81@gmail.com", False
    ) is None
    assert auth.get_authenticated_administrator(
        "outsider@example.com", True
    ) is None
    assert auth.get_authenticated_administrator(True, True) is None


def test_auth0_configuration_requires_shared_and_provider_settings(monkeypatch):
    monkeypatch.setattr(
        auth.st,
        "secrets",
        {
            "auth": {
                "redirect_uri": "http://localhost:8501/oauth2callback",
                "cookie_secret": "generated-secret",
                "auth0": {
                    "client_id": "client-id",
                    "client_secret": "client-secret",
                    "server_metadata_url": (
                        "https://example.auth0.com/.well-known/openid-configuration"
                    ),
                },
            }
        },
    )

    assert auth.is_auth0_configured()


def test_auth0_configuration_is_false_when_settings_are_missing(monkeypatch):
    monkeypatch.setattr(auth.st, "secrets", {"auth": {}})

    assert not auth.is_auth0_configured()
