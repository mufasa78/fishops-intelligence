"""Compare a FishOps SQLite source with the configured PostgreSQL database."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import MetaData, Table, and_, create_engine, func, inspect, select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fishops.config import PROSPECTS_SCHEMA, get_settings
from fishops.db.models import Base, ContactPoint, SuppressionEntry
from fishops.db.session import create_db_engine


def _same_value(left: object, right: object) -> bool:
    from datetime import datetime, timezone

    if isinstance(left, datetime) and isinstance(right, datetime):
        if left.tzinfo is None:
            left = left.replace(tzinfo=timezone.utc)
        if right.tzinfo is None:
            right = right.replace(tzinfo=timezone.utc)
        return left.astimezone(timezone.utc) == right.astimezone(timezone.utc)
    return left == right


def verify(sqlite_path: Path) -> list[str]:
    if not sqlite_path.is_file():
        raise FileNotFoundError(f"SQLite source database does not exist: {sqlite_path}")

    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        raise ValueError("FISHOPS_DATABASE_URL must point to PostgreSQL for verification.")

    source_engine = create_engine(
        f"sqlite:///{sqlite_path.resolve().as_posix()}",
        connect_args={"check_same_thread": False},
    )
    target_engine = create_db_engine(settings.database_url)
    failures: list[str] = []
    try:
        source_inspector = inspect(source_engine)
        target_inspector = inspect(target_engine)
        source_names = set(source_inspector.get_table_names())
        target_names = set(target_inspector.get_table_names(schema=PROSPECTS_SCHEMA))
        tables = [
            table
            for table in Base.metadata.sorted_tables
            if table.name in source_names
        ]
        missing_source = {
            table.name
            for table in Base.metadata.sorted_tables
            if table.name != "authentication_logs" and table.name not in source_names
        }
        if missing_source:
            failures.append(f"Missing SQLite source tables: {sorted(missing_source)}")

        source_metadata = MetaData()
        with source_engine.connect() as source, target_engine.connect() as target:
            for model_table in tables:
                if model_table.name not in target_names:
                    failures.append(f"Missing PostgreSQL table: {model_table.name}")
                    continue
                source_table = Table(
                    model_table.name,
                    source_metadata,
                    autoload_with=source_engine,
                )
                target_table = Base.metadata.tables[
                    f"{PROSPECTS_SCHEMA}.{model_table.name}"
                ]
                source_count = source.execute(
                    select(func.count()).select_from(source_table)
                ).scalar_one()
                target_count = target.execute(
                    select(func.count()).select_from(target_table)
                ).scalar_one()
                if source_count != target_count:
                    failures.append(
                        f"{model_table.name} row-count mismatch: "
                        f"SQLite={source_count}, PostgreSQL={target_count}"
                    )

                for column in model_table.columns:
                    if not column.nullable:
                        nulls = target.execute(
                            select(func.count())
                            .select_from(target_table)
                            .where(target_table.c[column.name].is_(None))
                        ).scalar_one()
                        if nulls:
                            failures.append(
                                f"{model_table.name}.{column.name} has {nulls} null values"
                            )

                unique_sets = [
                    tuple(column.name for column in constraint.columns)
                    for constraint in model_table.constraints
                    if constraint.__class__.__name__ == "UniqueConstraint"
                ]
                for columns in unique_sets:
                    duplicates = target.execute(
                        select(func.count())
                        .select_from(
                            select(*[target_table.c[name] for name in columns])
                            .group_by(*[target_table.c[name] for name in columns])
                            .having(func.count() > 1)
                            .subquery()
                        )
                    ).scalar_one()
                    if duplicates:
                        failures.append(
                            f"{model_table.name} has {duplicates} duplicate groups "
                            f"for {columns}"
                        )

                if source_count and target_count:
                    primary_key = list(model_table.primary_key.columns)[0]
                    source_sample = source.execute(
                        select(source_table).order_by(source_table.c[primary_key.name]).limit(1)
                    ).mappings().one()
                    target_sample = target.execute(
                        select(target_table)
                        .where(target_table.c[primary_key.name] == source_sample[primary_key.name])
                    ).mappings().one_or_none()
                    if target_sample is None or any(
                        not _same_value(
                            source_sample[column.name], target_sample[column.name]
                        )
                        for column in model_table.columns
                    ):
                        failures.append(f"{model_table.name} sample row mismatch")

                for connection, inspector, names, schema, label in (
                    (source, source_inspector, source_names, None, "SQLite"),
                    (target, target_inspector, target_names, PROSPECTS_SCHEMA, "PostgreSQL"),
                ):
                    for foreign_key in inspector.get_foreign_keys(
                        model_table.name, schema=schema
                    ):
                        referred_name = foreign_key["referred_table"]
                        if referred_name not in names:
                            continue
                        local_columns = foreign_key["constrained_columns"]
                        remote_columns = foreign_key["referred_columns"]
                        local_table = Table(
                            model_table.name,
                            MetaData(),
                            schema=schema,
                            autoload_with=connection.engine,
                        )
                        referred_schema = (
                            foreign_key.get("referred_schema") or schema
                        )
                        referred_table = Table(
                            referred_name,
                            MetaData(),
                            schema=referred_schema,
                            autoload_with=connection.engine,
                        )
                        join_condition = and_(
                            *[
                                local_table.c[local] == referred_table.c[remote]
                                for local, remote in zip(local_columns, remote_columns)
                            ]
                        )
                        missing_refs = connection.execute(
                            select(func.count())
                            .select_from(
                                local_table.outerjoin(referred_table, join_condition)
                            )
                            .where(
                                and_(
                                    *[
                                        local_table.c[column].is_not(None)
                                        for column in local_columns
                                    ]
                                ),
                                referred_table.c[remote_columns[0]].is_(None),
                            )
                        ).scalar_one()
                        if missing_refs:
                            failures.append(
                                f"{model_table.name} has {missing_refs} broken "
                                f"{label} foreign keys"
                            )

            if "contact_points" in target_names and "suppression_entries" in target_names:
                opted_out_without_entry = target.execute(
                    select(func.count())
                    .select_from(ContactPoint)
                    .where(
                        ContactPoint.is_opted_out.is_(True),
                        ~select(SuppressionEntry.id)
                        .where(
                            SuppressionEntry.channel == ContactPoint.channel,
                            SuppressionEntry.value_normalized
                            == ContactPoint.value_normalized,
                        )
                        .exists(),
                    )
                ).scalar_one()
                if opted_out_without_entry:
                    failures.append(
                        f"{opted_out_without_entry} opted-out contacts lack a suppression ledger entry"
                    )
    finally:
        source_engine.dispose()
        target_engine.dispose()

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sqlite-path",
        type=Path,
        default=ROOT / "data" / "fishops.db",
        help="Path to the original SQLite database; verification is read-only.",
    )
    args = parser.parse_args()
    try:
        failures = verify(args.sqlite_path)
    except (OSError, ValueError) as exc:
        print(f"Verification failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(
            f"Verification failed ({type(exc).__name__}). "
            "Check database connectivity and migration state.",
            file=sys.stderr,
        )
        return 1
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("Verification passed: row counts, foreign keys, constraints, samples, suppression ledger.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
