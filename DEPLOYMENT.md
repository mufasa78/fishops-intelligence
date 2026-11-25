# Deployment

## Prerequisites

- A private GitHub repository owned by FishOps.
- A Supabase PostgreSQL project and connection string.
- A Google OAuth web client configured for Streamlit's OIDC flow.
- Tracy's and Stanley's Google account emails configured as the only admins.

The repository is prepared for deployment, but no repository was created,
code pushed, or live app deployed from this workspace.

## Local configuration

1. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`.
2. Set the Google OIDC `client_id`, `client_secret`, `cookie_secret`, and
   callback `redirect_uri`. Do not commit `secrets.toml`.
3. Set `[database].url` to the Supabase PostgreSQL URL. It must include TLS and
   the `prospects` search path. Alternatively configure `FISHOPS_DATABASE_URL`.
4. Configure `[admins].email_1` as `mburutracy81@gmail.com` and
   `[admins].email_2` as `njorogestan12@gmail.com`.
5. Apply the schema and authentication audit migration:

   ```powershell
   python -m alembic upgrade head
   python init_schema.py
   ```

6. Run the tests and launch locally:

   ```powershell
   python -m pytest tests/ -v
   streamlit run app.py
   ```

Google OIDC credentials must list the local callback URI and the eventual
Streamlit Community Cloud callback URI as authorized redirect URIs.

## Private GitHub repository

1. Create a private repository named `fishops-prospect-intelligence` in the
   FishOps GitHub organization/account.
2. Review tracked files and confirm that `.env`, `.streamlit/secrets.toml`,
   `data/`, SQLite files, CSV exports, and logs are excluded.
3. Push only after the repository owner authorizes the operation.
4. Configure branch protection and limit repository access to maintainers.

No GitHub remote or deployment credentials are assumed by this project.

## Streamlit Community Cloud

1. Sign in to Streamlit Community Cloud and connect the authorized GitHub
   account.
2. Create an app from the private `fishops-prospect-intelligence` repository.
3. Select branch `main` and entrypoint `app.py`.
4. Select Python 3.11, matching local setup and the `requires-python` floor in
   `pyproject.toml`.
5. In app settings, add the `[auth]`, `[database]`, and `[admins]` sections
   from the example secrets file, using production values.
6. Set `[auth].redirect_uri` and Google's authorized redirect URI to the
   actual Streamlit app callback URL.
7. Deploy, then confirm that Supabase is reachable and the schema is initialized.
8. Test Tracy and Stanley's Google accounts individually, verify an
   unlisted account is denied, and test logout.
9. Confirm dashboard data is visible only after administrator authorization.

Never put OAuth credentials, cookie secrets, or database passwords in GitHub.
Deployment is not complete until the live URL and both authorized accounts have
been tested.
