# FishOps Prospect Intelligence

Internal prospecting and relationship intelligence for the Kenya aquaculture
value chain. The application preserves the existing collectors, unverified
candidate review flow, SQLAlchemy data model, and Streamlit dashboard.

## Local setup

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .streamlit\secrets.toml.example .streamlit\secrets.toml
```

Replace the example Google OAuth, database, and cookie-secret values in
`.streamlit\secrets.toml`. The two administrator emails are Tracy
Wambui Mburu (`mburutracy81@gmail.com`) and Stanley Gathekia
(`njorogestan12@gmail.com`). `.env` may instead supply
`FISHOPS_DATABASE_URL`, `FISHOPS_ADMIN_EMAIL_1`, and
`FISHOPS_ADMIN_EMAIL_2`.

The local database defaults to SQLite if no connection is configured.
Production uses Supabase PostgreSQL with all FishOps tables isolated in the
`prospects` schema. Never use SQLite as the sole production database on
Streamlit Community Cloud.

## Run and test

```powershell
python -m pytest tests/ -v
streamlit run app.py
```

Google OIDC must be configured before attempting the login flow. Scraped
records remain unverified until manually reviewed.

## Database setup and migration

Set the Supabase connection using `FISHOPS_DATABASE_URL` or
`[database].url` in Streamlit secrets, then apply Alembic migrations and
initialize the ORM schema:

```powershell
python -m alembic upgrade head
python init_schema.py
```

To copy a SQLite database to PostgreSQL without modifying the source:

```powershell
python scripts/migrate_sqlite_to_postgres.py --sqlite-path data\fishops.db
python scripts/verify_migration.py --sqlite-path data\fishops.db
```

See [DEPLOYMENT.md](DEPLOYMENT.md) for private GitHub and Streamlit Community
Cloud setup instructions.
# fishops-intelligence
