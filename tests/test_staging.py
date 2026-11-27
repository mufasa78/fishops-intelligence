"""Tests for database models and staging layer."""

from __future__ import annotations

import csv

import pytest
from sqlalchemy import select

import collect
from fishops.collectors.base import CandidateRecord
from fishops.db.models import (
    CollectionRun,
    ContactPoint,
    Organization,
    OutreachActivity,
    SourceRecord,
)
from fishops.db.session import init_db, session_scope
from fishops.staging import stage_candidates


@pytest.fixture
def engine(tmp_path):
    db_url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    return init_db(
        __import__("fishops.db.session", fromlist=["create_db_engine"]).create_db_engine(db_url)
    )


def _make_candidate(**overrides) -> CandidateRecord:
    defaults = dict(
        business_name="Test Fish Farm",
        source_name="Test Source",
        adapter_name="test_adapter",
        source_url="https://example.com/test",
        phone_raw="0712345678",
        location_text_raw="Sagana, Kirinyaga",
        country_code="KE",
    )
    defaults.update(overrides)
    record = CandidateRecord(**defaults)
    record.finalize()
    return record


class TestStaging:
    def test_new_candidate_creates_org_and_source_record(self, engine):
        candidate = _make_candidate()
        with session_scope(engine) as session:
            result = stage_candidates(session, [candidate])
        assert result["new"] == 1
        assert result["duplicate"] == 0
        with session_scope(engine) as session:
            orgs = session.execute(select(Organization)).scalars().all()
            assert len(orgs) == 1
            assert orgs[0].verification_status == "unverified"
            assert orgs[0].pipeline_stage == "discovered"
            records = session.execute(select(SourceRecord)).scalars().all()
            assert len(records) == 1

    def test_duplicate_fingerprint_is_skipped(self, engine):
        candidate = _make_candidate()
        with session_scope(engine) as session:
            stage_candidates(session, [candidate])
        with session_scope(engine) as session:
            result = stage_candidates(session, [candidate])
        assert result["duplicate"] == 1
        assert result["new"] == 0

    def test_contact_points_created_for_phone(self, engine):
        candidate = _make_candidate(phone_raw="0712345678")
        with session_scope(engine) as session:
            stage_candidates(session, [candidate])
        with session_scope(engine) as session:
            contacts = session.execute(
                select(ContactPoint).where(ContactPoint.channel == "phone")
            ).scalars().all()
            assert len(contacts) == 1
            assert contacts[0].verification_status == "unverified"
            assert contacts[0].is_opted_out is False

    def test_organization_name_normalization_merges(self, engine):
        c1 = _make_candidate(business_name="Sagana Fish Farm Ltd", phone_raw="0712000001")
        c2 = _make_candidate(business_name="Sagana Fish Farm Limited", phone_raw="0712000002")
        with session_scope(engine) as session:
            stage_candidates(session, [c1, c2])
            orgs = session.execute(select(Organization)).scalars().all()
        # Both should collapse to the same normalized name → one org
        assert len(orgs) == 1

    def test_collection_run_recorded(self, engine):
        candidates = [_make_candidate()]
        with session_scope(engine) as session:
            stage_candidates(session, candidates, adapter_name="test_run")
            runs = session.execute(select(CollectionRun)).scalars().all()
        assert len(runs) == 1
        assert runs[0].adapter_name == "test_run"
        assert runs[0].status == "completed"
        assert runs[0].items_new == 1

    def test_candidate_enriches_new_organization_with_location_and_coordinates(
        self, engine
    ):
        candidate = _make_candidate(
            city_town="Sagana",
            address_raw="Main road",
            latitude=0.0,
            longitude=0.0,
            website_raw="https://example.org",
        )

        with session_scope(engine) as session:
            stage_candidates(session, [candidate])

        with session_scope(engine) as session:
            org = session.execute(select(Organization)).scalar_one()

        assert org.city_town == "Sagana"
        assert org.address_raw == "Main road"
        assert org.latitude == 0.0
        assert org.longitude == 0.0
        assert org.website == "https://example.org"

    def test_zero_coordinates_are_not_treated_as_missing(self, engine):
        candidate = _make_candidate(latitude=1.5, longitude=37.0)
        with session_scope(engine) as session:
            session.add(
                Organization(
                    business_name=candidate.business_name,
                    normalized_name="test fish farm",
                    business_type="fish_farm",
                    country_code="KE",
                    latitude=0.0,
                    longitude=0.0,
                    pipeline_stage="discovered",
                    outreach_status="active",
                    verification_status="unverified",
                )
            )
        with session_scope(engine) as session:
            stage_candidates(session, [candidate])
        with session_scope(engine) as session:
            org = session.execute(select(Organization)).scalar_one()

        assert org.latitude == 0.0
        assert org.longitude == 0.0

    def test_verified_organization_is_not_enriched_from_candidate(self, engine):
        candidate = _make_candidate(
            county_inferred="Kiambu",
            website_raw="https://new.example.org",
            latitude=1.5,
        )
        with session_scope(engine) as session:
            session.add(
                Organization(
                    business_name=candidate.business_name,
                    normalized_name="test fish farm",
                    business_type="fish_farm",
                    country_code="KE",
                    county="Nairobi",
                    website="https://verified.example.org",
                    latitude=0.0,
                    pipeline_stage="verified_prospect",
                    outreach_status="active",
                    verification_status="verified",
                )
            )
        with session_scope(engine) as session:
            stage_candidates(session, [candidate])
        with session_scope(engine) as session:
            org = session.execute(select(Organization)).scalar_one()

        assert org.county == "Nairobi"
        assert org.website == "https://verified.example.org"
        assert org.latitude == 0.0


def test_outreach_activity_is_persisted_for_organization(engine):
    with session_scope(engine) as session:
        org = Organization(
            business_name="Follow-up Farm",
            normalized_name="follow-up farm",
            business_type="fish_farm",
            country_code="KE",
            pipeline_stage="discovered",
            outreach_status="active",
            verification_status="unverified",
        )
        session.add(org)
        session.flush()
        session.add(
            OutreachActivity(
                organization_id=org.id,
                activity_type="call",
                outcome="No answer",
                next_step="Call again",
                actor="admin@example.org",
            )
        )

    with session_scope(engine) as session:
        activity = session.execute(select(OutreachActivity)).scalar_one()
        assert activity.organization.business_name == "Follow-up Farm"
        assert activity.next_step == "Call again"


class TestOrganizationModel:
    def test_suppression_defaults(self, engine):
        with session_scope(engine) as session:
            org = Organization(
                business_name="Test Org",
                normalized_name="test org",
                business_type="fish_farm",
                country_code="KE",
                pipeline_stage="discovered",
                outreach_status="active",
                verification_status="unverified",
            )
            session.add(org)
            session.flush()
            assert org.is_suppressed is False
            assert org.suppressed_at is None


def test_sqlite_database_survives_engine_restart(tmp_path):
    db_url = f"sqlite:///{(tmp_path / 'persistent.db').as_posix()}"
    first_engine = init_db(
        __import__("fishops.db.session", fromlist=["create_db_engine"]).create_db_engine(db_url)
    )
    with session_scope(first_engine) as session:
        session.add(
            Organization(
                business_name="Persistent Farm",
                normalized_name="persistent farm",
                business_type="fish_farm",
                country_code="KE",
                pipeline_stage="discovered",
                outreach_status="active",
                verification_status="unverified",
            )
        )
    first_engine.dispose()

    restarted_engine = init_db(
        __import__("fishops.db.session", fromlist=["create_db_engine"]).create_db_engine(db_url)
    )
    with session_scope(restarted_engine) as session:
        organizations = session.execute(select(Organization)).scalars().all()

    assert [org.business_name for org in organizations] == ["Persistent Farm"]


def test_csv_import_does_not_run_default_live_collector(monkeypatch, tmp_path, capsys):
    database_path = tmp_path / "import.db"
    input_path = tmp_path / "public_contacts.csv"
    with input_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["business_name", "source_url"])
        writer.writeheader()
        writer.writerow(
            {
                "business_name": "Public Contact Organization",
                "source_url": "https://example.org/contact",
            }
        )

    monkeypatch.setenv("FISHOPS_DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    monkeypatch.setenv("FISHOPS_RAW_DIR", str(tmp_path / "raw"))
    monkeypatch.setitem(collect.ADAPTER_MAP, "goafrica", lambda **_: pytest.fail("live source ran"))

    assert collect.main(["--import-csv", str(input_path)]) == 0
    assert "New source records:   1" in capsys.readouterr().out
