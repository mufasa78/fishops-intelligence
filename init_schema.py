r"""
init_schema.py – One-time setup script.

Creates the ``prospects`` schema (isolated from the main FishOps ``public``
schema) and all Prospect Intelligence tables within it.

Run once against your Supabase database:
    .venv\Scripts\python.exe init_schema.py

Safe to re-run: uses CREATE SCHEMA IF NOT EXISTS and CREATE TABLE IF NOT EXISTS.
"""

from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.engine import make_url

from fishops.config import PROSPECTS_SCHEMA, get_settings
from fishops.db.session import init_db, create_db_engine


def main() -> int:
    settings = get_settings()
    url = make_url(settings.database_url)
    target = url.get_backend_name()
    if url.host:
        target += f" host={url.host}"
    if url.database:
        target += f" database={url.database}"
    print(f"Target: {target}")
    print(f"Schema: {PROSPECTS_SCHEMA}")
    print()

    if "sqlite" in settings.database_url:
        print("⚠️  Running against SQLite (no PostgreSQL connection is configured).")
        print(
            "   Set FISHOPS_DATABASE_URL (or SUPABASE_URL and DATABASE_PASSWORD) "
            "to target Supabase."
        )
        print()

    try:
        engine = create_db_engine(settings.database_url)
        init_db(engine)
        print(f"✅  Schema '{PROSPECTS_SCHEMA}' and all tables created successfully.")
        return 0
    except SQLAlchemyError as exc:
        print(
            f"❌  Schema init failed ({type(exc).__name__}). "
            "Check database connectivity and configured credentials."
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
