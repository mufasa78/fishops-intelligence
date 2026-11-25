"""Copy a FishOps SQLite database into the configured PostgreSQL database."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, Table, create_engine, func, inspect, select, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fishops.config import PROSPECTS_SCHEMA, get_settings
from fishops.db.models import Base
from fishops.db.session import create_db_engine, init_db


def _equal(left: object, right: object) -> bool:
    if isinstance(left, datetime) and isinstance(right, datetime):
        if left.tzinfo is None:
            left = left.replace(tzinfo=timezone.utc)
        if right.tzinfo is None:
            right = right.replace(tzinfo=timezone.utc)
        return left.astimezone(timezone.utc) == right.astimezone(timezone.utc)
    return left == right


def _same_record(existing: dict, incoming: dict) -> bool:
    return existing.keys() == incoming.keys() and all(
        _equal(existing[key], incoming[key]) for key in incoming
    )


def migrate(sqlite_path: Path) -> dict[str, dict[str, int]]:
    if not sqlite_path.is_file():
        raise FileNotFoundError(f"SQLite source database does not exist: {sqlite_path}")

    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        raise ValueError("FISHOPS_DATABASE_URL must point to PostgreSQL for migration.")

    source_engine = create_engine(
        f"sqlite:///{sqlite_path.resolve().as_posix()}",
        connect_args={"check_same_thread": False},
    )
    target_engine = None
    try:
        source_tables = set(inspect(source_engine).get_table_names())
        required_tables = {table.name for table in Base.metadata.sorted_tables} - {
            "authentication_logs"
        }
        missing_tables = required_tables - source_tables
        if missing_tables:
            raise RuntimeError(
                "SQLite source is missing required tables: "
                + ", ".join(sorted(missing_tables))
            )

        target_engine = create_db_engine(settings.database_url)
        config = Config(str(ROOT / "alembic.ini"))
        command.upgrade(config, "head")
        init_db(target_engine)

        metadata = MetaData()
        counts: dict[str, dict[str, int]] = {}
        ordered_tables = [
            table
            for table in Base.metadata.sorted_tables
            if table.name in source_tables
        ]
        with source_engine.connect() as source, target_engine.begin() as target:
            for model_table in ordered_tables:
                source_table = Table(
                    model_table.name,
                    metadata,
                    autoload_with=source_engine,
                )
                target_table = Base.metadata.tables[
                    f"{PROSPECTS_SCHEMA}.{model_table.name}"
                ]
                primary_key = list(target_table.primary_key.columns)
                if len(primary_key) != 1:
                    raise RuntimeError(
                        f"Expected a single primary key for {model_table.name}"
                    )
                primary_key = primary_key[0]
                copied = 0
                already_present = 0

                for source_row in source.execute(select(source_table)).mappings():
                    incoming = dict(source_row)
                    existing_row = target.execute(
                        select(target_table).where(
                            primary_key == incoming[primary_key.name]
                        )
                    ).mappings().one_or_none()
                    if existing_row is not None:
                        if not _same_record(dict(existing_row), incoming):
                            raise RuntimeError(
                                f"Conflicting destination row in {model_table.name} "
                                f"for id={incoming[primary_key.name]}"
                            )
                        already_present += 1
                        continue

                    target.execute(target_table.insert().values(**incoming))
                    copied += 1

                counts[model_table.name] = {
                    "copied": copied,
                    "already_present": already_present,
                }

            for model_table in ordered_tables:
                target_table = Base.metadata.tables[
                    f"{PROSPECTS_SCHEMA}.{model_table.name}"
                ]
                sequence_name = target.execute(
                    text(
                        "SELECT pg_get_serial_sequence(:table_name, 'id')"
                    ),
                    {"table_name": f"{PROSPECTS_SCHEMA}.{model_table.name}"},
                ).scalar_one()
                if sequence_name:
                    max_id = target.execute(
                        select(func.max(target_table.c.id))
                    ).scalar_one()
                    target.execute(
                        text(
                            "SELECT setval(CAST(:sequence_name AS regclass), "
                            "COALESCE(:max_id, 1), :has_rows)"
                        ),
                        {
                            "sequence_name": sequence_name,
                            "max_id": max_id,
                            "has_rows": max_id is not None,
                        },
                    )

        return counts
    finally:
        source_engine.dispose()
        if target_engine is not None:
            target_engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sqlite-path",
        type=Path,
        default=ROOT / "data" / "fishops.db",
        help="Path to the existing SQLite database (source is never modified).",
    )
    args = parser.parse_args()
    try:
        counts = migrate(args.sqlite_path)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Migration failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(
            f"Migration failed ({type(exc).__name__}). "
            "The SQLite source was not modified; destination data transfer did not complete.",
            file=sys.stderr,
        )
        return 1
    print("Migration completed.")
    for table, result in sorted(counts.items()):
        print(
            f"  {table}: copied={result['copied']}, "
            f"identical rows already present={result['already_present']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
