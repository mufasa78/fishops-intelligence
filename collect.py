"""
collect.py – FishOps multi-source prospect intelligence collector CLI.

Usage:
    python collect.py --sources goafrica kefs osm wikidata --max-pages 5 --delay 3
    python collect.py --sources goafrica --max-pages 3
    python collect.py --import-csv path/to/register.csv --source-name "KEFS Manual Export"
    python collect.py --dry-run   # collect only, skip DB staging
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from fishops.collectors import (
    GoAfricaCollector,
    KEFSCollector,
    OSMOverpassCollector,
    WikidataCollector,
    deduplicate_candidates,
    export_candidates_csv,
    load_candidates_from_csv,
)
from fishops.collectors.base import CandidateRecord
from fishops.config import get_settings
from fishops.db.session import init_db, session_scope
from fishops.staging import stage_candidates

ADAPTER_MAP = {
    "goafrica": GoAfricaCollector,
    "kefs": KEFSCollector,
    "osm": OSMOverpassCollector,
    "wikidata": WikidataCollector,
}


def build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="FishOps multi-source aquaculture prospect collector",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--sources",
        nargs="+",
        choices=list(ADAPTER_MAP.keys()),
        default=None,
        metavar="SOURCE",
        help=(
            "One or more collection sources: "
            f"{', '.join(ADAPTER_MAP.keys())}; defaults to Go Africa Online "
            "unless importing a CSV"
        ),
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=5,
        help="Maximum paginated pages per web-based adapter",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=3.0,
        help="Minimum seconds between HTTP requests",
    )
    parser.add_argument(
        "--import-csv",
        type=str,
        default="",
        metavar="PATH",
        help="Import an existing CSV instead of (or in addition to) live collection",
    )
    parser.add_argument(
        "--source-name",
        type=str,
        default="",
        metavar="NAME",
        help="Friendly source name for --import-csv records",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Collect and export CSV without writing to the database",
    )
    parser.add_argument(
        "--no-robots",
        action="store_true",
        help="Disable robots.txt compliance checking (use with caution)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="",
        metavar="DIR",
        help="Override directory for CSV output",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argparser().parse_args(argv)
    settings = get_settings()
    source_keys = args.sources
    if source_keys is None:
        source_keys = [] if args.import_csv else ["goafrica"]

    all_records: list[CandidateRecord] = []

    # --- Live collection ---
    for source_key in source_keys:
        cls = ADAPTER_MAP[source_key]
        collector = cls(
            delay=args.delay,
            respect_robots=not args.no_robots,
        )
        try:
            records = collector.collect(max_pages=args.max_pages)
            all_records.extend(records)
        except Exception as exc:
            print(f"[ERROR] {source_key}: {exc}", file=sys.stderr)

    # --- CSV import ---
    if args.import_csv:
        try:
            imported = load_candidates_from_csv(
                args.import_csv,
                adapter_name="csv_import",
                source_name=args.source_name or None,
            )
            all_records.extend(imported)
            print(f"[CSV Import] Loaded {len(imported)} record(s) from {args.import_csv}")
        except Exception as exc:
            print(f"[ERROR] CSV import failed: {exc}", file=sys.stderr)

    if not all_records:
        print("No candidates collected.")
        return 0

    # --- Deduplication ---
    unique = deduplicate_candidates(all_records)
    print(f"\nTotal collected: {len(all_records)}")
    print(f"Unique (by fingerprint): {len(unique)}")

    # --- CSV export ---
    output_dir = Path(args.output_dir) if args.output_dir else settings.raw_output_dir
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    sources_tag = "_".join(sorted(source_keys)) or "import"
    csv_path = output_dir / f"fishops_candidates_{sources_tag}_{timestamp}.csv"

    export_candidates_csv(unique, csv_path)
    print(f"CSV exported: {csv_path}")

    if args.dry_run:
        print("Dry-run: database staging skipped.")
        return 0

    # --- Stage into database ---
    engine = init_db()
    with session_scope(engine) as session:
        result = stage_candidates(session, unique, adapter_name=sources_tag, csv_path=str(csv_path))
        print(
            f"\nDatabase staged:"
            f"\n  New source records:   {result['new']}"
            f"\n  Duplicate skips:      {result['duplicate']}"
            f"\n  Errors:               {result['errors']}"
        )

    print("\nAll records are UNVERIFIED and require human review before outreach.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
