"""Tests for database models and staging layer."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from fishops.collectors.base import CandidateRecord
from fishops.db.models import (
    CollectionRun,
    Organization,
    SourceRecord,
    ContactPoint,
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
