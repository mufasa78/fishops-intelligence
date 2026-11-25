"""
Application configuration for FishOps Prospect Intelligence.

Environment variable loading order:
  1. `.env` file in the project root (via python-dotenv)
  2. Shell environment variables
  3. Hard-coded defaults (SQLite only, never production secrets)

SCHEMA ISOLATION:
  All FishOps Prospect Intelligence tables live in the ``prospects`` schema
  inside Supabase, completely separated from the main FishOps platform tables
  which live in the default ``public`` schema.  The Supabase service-role key
  is not used for database access; configure a PostgreSQL connection URL whose
  database role has access to the isolated ``prospects`` schema.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

# Load .env if python-dotenv is available (graceful fallback if not)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = BASE_DIR / "data"
DEFAULT_RAW_DIR = DEFAULT_DATA_DIR / "raw"

# ---------------------------------------------------------------------------
# Schema isolation: ALL prospects tables live in schema ``prospects``,
# NOT in ``public`` which is used by the main FishOps platform.
# ---------------------------------------------------------------------------
PROSPECTS_SCHEMA = "prospects"


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from environment variables with safe defaults."""

    database_url: str
    raw_output_dir: Path
    default_country_code: str = "KE"
    db_schema: str = PROSPECTS_SCHEMA
    user_agent: str = (
        "FishOpsResearchBot/1.0 "
        "(business research; contact: admin@fishops.example)"
    )
    min_request_delay_seconds: float = 2.0
    request_timeout_seconds: int = 25

    # Supabase URL used when constructing a PostgreSQL connection URL.
    supabase_url: str = ""


def _build_supabase_sqlalchemy_url() -> str:
    """
    Build a SQLAlchemy-compatible postgresql+psycopg2 URL from Supabase env vars.

    Uses the ``prospects`` schema via search_path so SQLAlchemy operates in
    the isolated schema without touching the ``public`` schema reserved for
    the official FishOps platform.

    Priority: FISHOPS_DATABASE_URL > Streamlit database secret > auto-build.
    """
    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    db_password = os.getenv("DATABASE_PASSWORD", "")

    if not supabase_url or not db_password:
        return ""

    try:
        project_ref = supabase_url.split("://")[1].split(".")[0]
    except (IndexError, AttributeError):
        return ""

    # Allow explicit override of pooler host or default to the verified cluster host
    pooler_host = os.getenv("SUPABASE_DB_HOST", "aws-1-eu-west-1.pooler.supabase.com")
    pooler_port = os.getenv("SUPABASE_DB_PORT", "5432")

    import urllib.parse
    safe_password = urllib.parse.quote(db_password, safe="")

    return (
        f"postgresql+psycopg2://postgres.{project_ref}:{safe_password}"
        f"@{pooler_host}:{pooler_port}"
        f"/postgres"
        f"?sslmode=require&options=-csearch_path%3D{PROSPECTS_SCHEMA}%2Cpublic"
    )


def get_settings() -> Settings:
    """Return runtime configuration, preferring Supabase over local SQLite."""
    raw_dir = Path(os.getenv("FISHOPS_RAW_DIR", str(DEFAULT_DATA_DIR / "raw")))

    # Determine database URL
    db_url = os.getenv("FISHOPS_DATABASE_URL", "")

    if not db_url:
        try:
            db_url = st.secrets.get("database", {}).get("url", "")
        except StreamlitSecretNotFoundError:
            pass

    if not db_url:
        db_url = _build_supabase_sqlalchemy_url()

    if not db_url:
        # Fallback to local SQLite for local development / testing
        data_dir = Path(os.getenv("FISHOPS_DATA_DIR", str(DEFAULT_DATA_DIR)))
        data_dir.mkdir(parents=True, exist_ok=True)
        db_url = f"sqlite:///{(data_dir / 'fishops.db').as_posix()}"

    raw_dir.mkdir(parents=True, exist_ok=True)

    return Settings(
        database_url=db_url,
        raw_output_dir=raw_dir,
        default_country_code=os.getenv("FISHOPS_DEFAULT_COUNTRY", "KE").upper(),
        db_schema=PROSPECTS_SCHEMA,
        supabase_url=os.getenv("SUPABASE_URL", ""),
    )
