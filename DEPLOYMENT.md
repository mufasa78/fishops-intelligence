# Deployment

## Prerequisites

- The existing public GitHub repository `mufasa78/fishops-intelligence`.
- A Supabase PostgreSQL project and connection string.
- An Auth0 application configured for the local and production Streamlit
  OAuth callback URLs.

The live app has not been deployed from this workspace.

Production URL: https://fishops-intelligence-4ofjpgfc6zyhsxxuafvqvz.streamlit.app/

## Local configuration

1. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`.
2. Set `[auth.auth0].client_secret` and `[auth].cookie_secret`. Keep both
   values private; use a unique random cookie secret.
3. Set `[database].url` to the Supabase PostgreSQL URL. It must include TLS and
   the `prospects` search path. Alternatively configure `FISHOPS_DATABASE_URL`.
4. Configure `[admins].email_1` as `mburutracy81@gmail.com` and
   `[admins].email_2` as `njorogestan12@gmail.com`.
5. In Auth0, require verified email for both allowlisted administrator
   accounts. Add `http://localhost:8501/oauth2callback` as a local callback and
   the production `/oauth2callback` URL below as a production callback.
6. Apply the schema and migrations:

   ```powershell
   python -m alembic upgrade head
   python init_schema.py
   ```

7. Run the tests and launch locally:

   ```powershell
   python -m pytest tests/ -v
   streamlit run app.py
   ```

## GitHub repository

1. Use the existing `mufasa78/fishops-intelligence` repository and `main`
   branch.
2. Review tracked files and confirm that `.env`, `.streamlit/secrets.toml`,
   `data/`, SQLite files, CSV exports, and logs are excluded.
3. Keep all database credentials and Supabase keys out of the public
   repository.
4. Configure branch protection and restrict write access to maintainers.

## Streamlit Community Cloud

1. Sign in to Streamlit Community Cloud and connect the authorized GitHub
   account.
2. Create an app from `mufasa78/fishops-intelligence`.
3. Select branch `main` and entrypoint `app.py`.
4. Select Python 3.11, matching local setup and the `requires-python` floor in
   `pyproject.toml`.
5. In app settings, add the `[auth]`, `[auth.auth0]`, `[database]`, and
   `[admins]` sections from the example secrets file, using production values.
6. Confirm Auth0 allows the production callback URL and both administrator
   accounts have verified email addresses.
7. Deploy, then confirm that Supabase is reachable and the schema is initialized.
8. Test sign-in with both allowlisted accounts, confirm an unlisted or
   unverified email is denied, and test logout.
9. Confirm dashboard data is visible only after administrator authorization.

Never put Auth0 secrets, passwords, or database credentials in GitHub.
Deployment is not complete until the live URL and both authorized accounts have
been tested.

## Prospect workflow

New CSV and public-directory data is staged as unverified. Operators should
preview imports, review candidates, verify organizations and contact details,
and record human outreach and next steps in the app. No automated messages are
sent. The BusinessList collector uses only its public fish-merchants page; do
not attempt to retrieve paid directory exports.
