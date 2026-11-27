"""
CSV import adapter for user-provided business directories and registers.

The importer accepts FishOps columns plus common directory-export headers
such as name, phone, address, city, lat, lng, and url.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import pandas as pd

from fishops.collectors.base import CandidateRecord
from fishops.normalization import clean_text

_COLUMN_ALIASES = {
    "name": "business_name",
    "company_name": "business_name",
    "organization_name": "business_name",
    "phone": "phone_raw",
    "email": "email_raw",
    "website": "website_raw",
    "url": "website_raw",
    "lat": "latitude",
    "lng": "longitude",
    "lon": "longitude",
    "address": "address_raw",
    "city": "city_town",
    "town": "city_town",
    "county": "county_inferred",
    "country": "country_name",
}


def _read_csv(source: str | Path | BinaryIO) -> tuple[pd.DataFrame, str]:
    if isinstance(source, (str, Path)):
        csv_path = Path(source)
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")
        return (
            pd.read_csv(
                csv_path,
                dtype=str,
                keep_default_na=False,
                encoding_errors="replace",
            ),
            csv_path.name,
        )

    source.seek(0)
    return (
        pd.read_csv(
            source,
            dtype=str,
            keep_default_na=False,
            encoding_errors="replace",
        ),
        getattr(source, "name", "uploaded.csv"),
    )


def _country_code(value: str, default_country_code: str, row_number: int) -> str:
    country = clean_text(value)
    if not country:
        return default_country_code.upper()
    if country.lower() in {"kenya", "republic of kenya"}:
        return "KE"
    if len(country) == 2 and country.isalpha():
        return country.upper()
    raise ValueError(
        f"CSV row {row_number}: unsupported country value {country!r}; "
        "use an ISO 3166-1 alpha-2 code or Kenya."
    )


def _optional_float(value: str, column: str, row_number: int) -> float | None:
    cleaned = clean_text(value)
    if not cleaned:
        return None
    try:
        number = float(cleaned)
    except ValueError as exc:
        raise ValueError(
            f"CSV row {row_number}: {column} must be a number, got {cleaned!r}."
        ) from exc
    bounds = {
        "latitude": (-90, 90),
        "longitude": (-180, 180),
    }
    if column in bounds and not bounds[column][0] <= number <= bounds[column][1]:
        lower, upper = bounds[column]
        raise ValueError(
            f"CSV row {row_number}: {column} must be between {lower} and {upper}."
        )
    return number


def load_candidates_from_csv(
    csv_source: str | Path | BinaryIO | BytesIO,
    adapter_name: str = "csv_import",
    source_name: str | None = None,
    source_url: str = "",
    default_country_code: str = "KE",
) -> list[CandidateRecord]:
    """
    Read a CSV export and return CandidateRecord objects.

    Headers are case-insensitive. Common directory fields are mapped into the
    FishOps candidate schema; all original columns are retained as provenance.
    Rows without a business name are skipped.
    """
    df, filename = _read_csv(csv_source)
    df.columns = [
        str(column).strip().lower().replace(" ", "_").replace("-", "_")
        for column in df.columns
    ]

    for alias, canonical in _COLUMN_ALIASES.items():
        if canonical not in df.columns and alias in df.columns:
            df[canonical] = df[alias]

    effective_source = source_name or f"CSV import: {filename}"
    records: list[CandidateRecord] = []

    for row_number, (_, row) in enumerate(df.iterrows(), start=2):
        def cell(key: str) -> str:
            return clean_text(str(row.get(key, "")))

        name = cell("business_name")
        if not name:
            continue

        address = cell("address_raw")
        city = cell("city_town")
        state = cell("state")
        county = cell("county_inferred")
        location = cell("location_text_raw")
        if not location:
            location = ", ".join(
                value
                for value in (
                    address,
                    city,
                    county or state,
                    cell("zip"),
                    cell("postal_code"),
                )
                if value
            )

        country_code = _country_code(
            cell("country_name") or cell("country_code"),
            default_country_code,
            row_number,
        )
        category_text = " ".join(
            value
            for value in (
                cell("primary_category_name"),
                cell("category_name"),
                cell("business_type_hint"),
            )
            if value
        )
        raw_text = " | ".join(value for value in (category_text, location) if value)
        payload = {
            str(column): str(value)
            for column, value in row.items()
            if clean_text(str(value))
        }

        record = CandidateRecord(
            business_name=name,
            source_name=effective_source,
            adapter_name=adapter_name,
            source_url=cell("source_url") or source_url,
            external_id=cell("external_id"),
            phone_raw=cell("phone_raw"),
            phone_normalized=cell("phone_normalized"),
            email_raw=cell("email_raw"),
            website_raw=cell("website_raw"),
            profile_url=cell("profile_url"),
            county_inferred=county,
            city_town=city,
            address_raw=address,
            location_text_raw=location,
            latitude=_optional_float(cell("latitude"), "latitude", row_number),
            longitude=_optional_float(cell("longitude"), "longitude", row_number),
            business_type_hint=cell("business_type_hint") or "unknown",
            raw_text=raw_text,
            raw_payload=payload,
            country_code=country_code,
            fingerprint=cell("fingerprint"),
        )
        records.append(record.finalize())

    return records
