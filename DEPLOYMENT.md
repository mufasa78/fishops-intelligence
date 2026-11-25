# Deployment

## Prerequisites

- The existing public GitHub repository `mufasa78/fishops-intelligence`.
- A Supabase PostgreSQL project and connection string.
- Supabase Auth email/password enabled, with individual accounts for Tracy and
  Stanley.

The application code and source collection documentation have been pushed. The
live app has not been deployed from this workspace.

Production URL: https://fishops-intelligence-4ofjpgfc6zyhsxxuafvqvz.streamlit.app/

## Local configuration

1. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`.
2. Set `[supabase].url` and `[supabase].publishable_key` to the project URL
   and publishable (or legacy anon) key. Never use a service-role key.
3. Set `[database].url` to the Supabase PostgreSQL URL. It must include TLS and
   the `prospects` search path. Alternatively configure `FISHOPS_DATABASE_URL`.
4. Configure `[admins].email_1` as `mburutracy81@gmail.com` and
   `[admins].email_2` as `njorogestan12@gmail.com`.
5. In Supabase Auth, invite each administrator individually and disable public
   sign-ups. Set the Auth **Site URL** and allowed redirect URL to the exact
   production URL above. The invite redirect opens the app's password setup
   screen; each administrator chooses a unique password of at least 12
   characters. The password is sent directly from the browser to Supabase Auth.
   The app's invitation flow validates the invited email against the admin
   allowlist and never stores the invite token or password on the app server.
6. Apply the schema and authentication audit migration:

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
5. In app settings, add the `[supabase]`, `[database]`, and `[admins]` sections
   from the example secrets file, using production values.
6. Confirm Supabase Auth public sign-ups are disabled and the Site URL and
   redirect allowlist point to the official production URL.
7. Deploy, then confirm that Supabase is reachable and the schema is initialized.
8. Send a test invitation to each administrator and verify each invite opens
   the password setup screen. Then test email/password sign-in, confirm an
   unlisted email is denied, and test logout.
9. Confirm dashboard data is visible only after administrator authorization.

Never put Supabase keys, passwords, or database credentials in GitHub.
Deployment is not complete until the live URL and both authorized accounts have
been tested.
