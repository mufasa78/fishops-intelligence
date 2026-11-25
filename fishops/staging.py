"""
Staging layer: load CandidateRecords into the database as SourceRecords
and auto-create Organization shells for first-seen candidates.

Rules:
- Never overwrite a manually verified value with a scraped value.
- Never automatically mark a scraped contact as verified.
- If a fingerprint already exists in source_records → mark as duplicate.
- If an organization with the same normalized name + country exists → link it.
- Otherwise create a new Organization in the 'discovered' pipeline stage.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from fishops.collectors.base import CandidateRecord
from fishops.db.models import (
    CollectionRun,
    ContactPoint,
    Organization,
    SourceRecord,
)
from fishops.normalization import clean_text, normalize_business_name


def _find_existing_organization(
    session: Session, normalized_name: str, country_code: str
) -> Organization | None:
    """Return an existing Organization with identical normalized name and country, or None."""
    result = session.execute(
        select(Organization)
        .where(Organization.normalized_name == normalized_name)
        .where(Organization.country_code == country_code)
        .limit(1)
    ).scalars().first()
    return result


def _create_organization_shell(candidate: CandidateRecord, session: Session) -> Organization:
    """Create a minimal discovered Organization shell from a candidate record."""
    org = Organization(
        business_name=candidate.business_name,
        normalized_name=normalize_business_name(candidate.business_name),
        business_type=candidate.business_type_hint,
        country_code=candidate.country_code,
        county=candidate.county_inferred or None,
        website=candidate.website_raw or None,
        pipeline_stage="discovered",
        outreach_status="active",
        verification_status="unverified",
    )
    session.add(org)
    session.flush()  # populate org.id
    return org


def _create_contact_points_from_candidate(
    candidate: CandidateRecord,
    org: Organization,
    source_record: SourceRecord,
    session: Session,
) -> None:
    """Add ContactPoint rows for phone and/or email if present in the candidate."""
    contacts: list[tuple[str, str, str]] = []

    if candidate.phone_raw:
        contacts.append(("phone", candidate.phone_raw, candidate.phone_normalized))
    if candidate.email_raw:
        contacts.append(("email", candidate.email_raw, ""))
    if candidate.website_raw:
        contacts.append(("website", candidate.website_raw, ""))

    for channel, value_raw, value_normalized in contacts:
        cp = ContactPoint(
            organization_id=org.id,
            source_record_id=source_record.id,
            channel=channel,
            value_raw=value_raw,
            value_normalized=value_normalized or None,
            verification_status="unverified",
            lawful_basis="unknown",
            is_primary=False,
            is_opted_out=False,
        )
        session.add(cp)


def stage_candidates(
    session: Session,
    candidates: list[CandidateRecord],
    adapter_name: str = "collector",
    csv_path: str = "",
) -> dict[str, int]:
    """
    Stage candidates into source_records and organizations.

    Returns counts: {'new': int, 'duplicate': int, 'errors': int}.
    """
    run = CollectionRun(
        adapter_name=adapter_name,
        status="running",
        items_found=len(candidates),
        output_csv_path=csv_path or None,
    )
    session.add(run)
    session.flush()

    counts: dict[str, int] = {"new": 0, "duplicate": 0, "errors": 0}

    for candidate in candidates:
        try:
            # Duplicate check on fingerprint
            existing_record = session.execute(
                select(SourceRecord)
                .where(SourceRecord.fingerprint == candidate.fingerprint)
                .limit(1)
            ).scalars().first()

            if existing_record is not None:
                counts["duplicate"] += 1
                continue

            # Find or create organization
            norm_name = normalize_business_name(candidate.business_name)
            org = _find_existing_organization(session, norm_name, candidate.country_code)
            if org is None:
                org = _create_organization_shell(candidate, session)

            payload_json = json.dumps(candidate.raw_payload, ensure_ascii=False) if candidate.raw_payload else None

            source_record = SourceRecord(
                collection_run_id=run.id,
                matched_organization_id=org.id,
                source_name=candidate.source_name,
                adapter_name=candidate.adapter_name,
                source_url=candidate.source_url,
                profile_url=candidate.profile_url or None,
                external_id=candidate.external_id or None,
                business_name_raw=candidate.business_name,
                business_type_hint=candidate.business_type_hint,
                phone_raw=candidate.phone_raw or None,
                phone_normalized=candidate.phone_normalized or None,
                email_raw=candidate.email_raw or None,
                website_raw=candidate.website_raw or None,
                county_inferred=candidate.county_inferred or None,
                location_text_raw=candidate.location_text_raw or None,
                latitude=candidate.latitude,
                longitude=candidate.longitude,
                raw_text=candidate.raw_text or None,
                raw_payload_json=payload_json,
                fingerprint=candidate.fingerprint,
                review_status="pending",
            )
            session.add(source_record)
            session.flush()

            _create_contact_points_from_candidate(candidate, org, source_record, session)
            counts["new"] += 1

        except Exception as exc:
            counts["errors"] += 1
            print(f"[Stage error] {candidate.business_name}: {exc}")

    run.status = "completed"
    run.finished_at = datetime.now(timezone.utc)
    run.items_new = counts["new"]
    run.items_duplicate = counts["duplicate"]

    return counts
