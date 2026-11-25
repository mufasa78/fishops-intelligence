"""
CSV import adapter.

Loads a CSV file of raw candidates (e.g., previously exported by another
collector run, a manual export, or a register spreadsheet) into CandidateRecord
objects for deduplication and database staging.

Required CSV column: ``business_name``  (all others optional).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from fishops.collectors.base import CandidateRecord
from fishops.normalization import clean_text


def load_candidates_from_csv(
    csv_path: str | Path,
    adapter_name: str = "csv_import",
    source_name: str | None = None,
    default_country_code: str = "KE",
) -> list[CandidateRecord]:
    """
    Read a CSV export and return CandidateRecord objects.

    - Column mapping is case-insensitive.
    - Rows without a recognizable business name are skipped.
    - Existing fingerprints in the CSV are reused if present (avoid re-fingerprinting
      already-deduplicated exports); new fingerprints are computed otherwise.
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False, encoding_errors="replace")
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]  # type: ignore[assignment]

    effective_source = source_name or f"CSV import: {csv_path.name}"
    records: list[CandidateRecord] = []

    for _, row in df.iterrows():
        def cell(key: str) -> str:
            return clean_text(str(row.get(key, "")))

        name = cell("business_name")
        if not name:
            continue

        raw_payload: dict[str, Any] = {k: v for k, v in row.items() if v and k not in {
            "business_name", "phone_raw", "phone_normalized", "email_raw", "website_raw",
            "profile_url", "source_url", "source_name", "adapter_name", "county_inferred",
            "location_text_raw", "latitude", "longitude", "business_type_hint",
            "raw_text", "fingerprint", "collected_at", "verification_status",
            "review_required", "country_code", "external_id",
        }}

        lat_raw = cell("latitude")
        lon_raw = cell("longitude")
        lat: float | None = float(lat_raw) if lat_raw else None
        lon: float | None = float(lon_raw) if lon_raw else None

        record = CandidateRecord(
            business_name=name,
            source_name=effective_source,
            adapter_name=adapter_name,
            source_url=cell("source_url"),
            external_id=cell("external_id"),
            phone_raw=cell("phone_raw"),
            phone_normalized=cell("phone_normalized"),
            email_raw=cell("email_raw"),
            website_raw=cell("website_raw"),
            profile_url=cell("profile_url"),
            county_inferred=cell("county_inferred"),
            location_text_raw=cell("location_text_raw"),
            latitude=lat,
            longitude=lon,
            business_type_hint=cell("business_type_hint") or "unknown",
            raw_text=cell("raw_text"),
            raw_payload=raw_payload,
            country_code=cell("country_code") or default_country_code,
            fingerprint=cell("fingerprint"),
        )
        record.finalize()
        records.append(record)

    return records
