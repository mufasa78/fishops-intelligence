"""SQLAlchemy ORM models for FishOps Prospect Intelligence.

SCHEMA: All tables live in the ``prospects`` schema (not ``public``).
This isolates Prospect Intelligence data from the main FishOps platform
tables that live in ``public``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# ---------------------------------------------------------------------------
# Schema constant – single source of truth for the isolated schema name.
# ---------------------------------------------------------------------------
_SCHEMA = "prospects"


def utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base declarative class for all FishOps Prospect Intelligence models."""


class Organization(Base):
    """Aquaculture value-chain business, hatchery, farm, or institutional prospect."""

    __tablename__ = "organizations"
    __table_args__ = {"schema": _SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    business_type: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown", index=True)
    registration_number: Mapped[str | None] = mapped_column(String(120), nullable=True)

    country_code: Mapped[str] = mapped_column(String(8), nullable=False, default="KE", index=True)
    county: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    city_town: Mapped[str | None] = mapped_column(String(120), nullable=True)
    address_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    website: Mapped[str | None] = mapped_column(String(512), nullable=True)

    pipeline_stage: Mapped[str] = mapped_column(String(64), nullable=False, default="discovered", index=True)
    outreach_status: Mapped[str] = mapped_column(String(64), nullable=False, default="active", index=True)

    verification_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unverified", index=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    verification_method: Mapped[str | None] = mapped_column(String(120), nullable=True)
    verification_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_suppressed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    suppression_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    suppressed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    farm_profile: Mapped[FarmProfile | None] = relationship(
        back_populates="organization", cascade="all, delete-orphan", uselist=False
    )
    contact_points: Mapped[list[ContactPoint]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    person_links: Mapped[list[OrganizationPerson]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    source_records: Mapped[list[SourceRecord]] = relationship(
        back_populates="matched_organization"
    )
    outreach_activities: Mapped[list[OutreachActivity]] = relationship(
        back_populates="organization"
    )


class Person(Base):
    """Individual contact (owner, manager, director, procurement officer)."""

    __tablename__ = "people"
    __table_args__ = {"schema": _SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    default_role: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_suppressed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    suppression_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    suppressed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    organization_links: Mapped[list[OrganizationPerson]] = relationship(
        back_populates="person", cascade="all, delete-orphan"
    )
    contact_points: Mapped[list[ContactPoint]] = relationship(
        back_populates="person", cascade="all, delete-orphan"
    )


class OrganizationPerson(Base):
    """Many-to-many link between organizations and people with role metadata."""

    __tablename__ = "organization_people"
    __table_args__ = (
        UniqueConstraint("organization_id", "person_id", name="uq_org_person"),
        {"schema": _SCHEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey(f"{_SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    person_id: Mapped[int] = mapped_column(
        ForeignKey(f"{_SCHEMA}.people.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    organization: Mapped[Organization] = relationship(back_populates="person_links")
    person: Mapped[Person] = relationship(back_populates="organization_links")


class FarmProfile(Base):
    """Operational aquaculture intelligence attached to an organization."""

    __tablename__ = "farm_profiles"
    __table_args__ = {"schema": _SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey(f"{_SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    species: Mapped[str | None] = mapped_column(Text, nullable=True)
    production_system: Mapped[str | None] = mapped_column(String(255), nullable=True)
    estimated_capacity_tons: Mapped[float | None] = mapped_column(Float, nullable=True)
    pond_or_cage_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_hatchery: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_processing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    current_challenges: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    organization: Mapped[Organization] = relationship(back_populates="farm_profile")


class CollectionRun(Base):
    """Audit record for each collector script execution or CSV import."""

    __tablename__ = "collection_runs"
    __table_args__ = {"schema": _SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    adapter_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    items_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_new: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_duplicate: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_csv_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    source_records: Mapped[list[SourceRecord]] = relationship(back_populates="collection_run")


class SourceRecord(Base):
    """Raw collected candidate record with full source provenance and review state."""

    __tablename__ = "source_records"
    __table_args__ = {"schema": _SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    collection_run_id: Mapped[int | None] = mapped_column(
        ForeignKey(f"{_SCHEMA}.collection_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    matched_organization_id: Mapped[int | None] = mapped_column(
        ForeignKey(f"{_SCHEMA}.organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )

    source_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    adapter_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    profile_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    business_name_raw: Mapped[str] = mapped_column(String(255), nullable=False)
    business_type_hint: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    phone_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone_normalized: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    email_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website_raw: Mapped[str | None] = mapped_column(String(512), nullable=True)
    country_code: Mapped[str] = mapped_column(String(8), nullable=False, default="KE")
    county_inferred: Mapped[str | None] = mapped_column(String(120), nullable=True)
    location_text_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    collection_run: Mapped[CollectionRun | None] = relationship(back_populates="source_records")
    matched_organization: Mapped[Organization | None] = relationship(back_populates="source_records")
    contact_points: Mapped[list[ContactPoint]] = relationship(back_populates="source_record")


class ContactPoint(Base):
    """Individual phone, WhatsApp, email, or web contact with verification & consent state."""

    __tablename__ = "contact_points"
    __table_args__ = {"schema": _SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey(f"{_SCHEMA}.organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    person_id: Mapped[int | None] = mapped_column(
        ForeignKey(f"{_SCHEMA}.people.id", ondelete="CASCADE"), nullable=True, index=True
    )
    source_record_id: Mapped[int | None] = mapped_column(
        ForeignKey(f"{_SCHEMA}.source_records.id", ondelete="SET NULL"), nullable=True
    )

    channel: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    value_raw: Mapped[str] = mapped_column(String(512), nullable=False)
    value_normalized: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    verification_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unverified", index=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    verification_method: Mapped[str | None] = mapped_column(String(120), nullable=True)

    lawful_basis: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    is_opted_out: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    opted_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opt_out_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    organization: Mapped[Organization | None] = relationship(back_populates="contact_points")
    person: Mapped[Person | None] = relationship(back_populates="contact_points")
    source_record: Mapped[SourceRecord | None] = relationship(back_populates="contact_points")


class OutreachActivity(Base):
    """Manual outreach and follow-up history for an organization."""

    __tablename__ = "outreach_activities"
    __table_args__ = {"schema": _SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey(f"{_SCHEMA}.organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    contact_point_id: Mapped[int | None] = mapped_column(
        ForeignKey(f"{_SCHEMA}.contact_points.id", ondelete="SET NULL"),
        nullable=True,
    )
    activity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    outcome: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_step: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_step_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    organization: Mapped[Organization] = relationship(
        back_populates="outreach_activities"
    )
    contact_point: Mapped[ContactPoint | None] = relationship()


class SuppressionEntry(Base):
    """Global Kenya DPA / ODPC suppression list preventing outreach to opted-out identifiers."""

    __tablename__ = "suppression_entries"
    __table_args__ = {"schema": _SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    value_raw: Mapped[str] = mapped_column(String(512), nullable=False)
    value_normalized: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by: Mapped[str] = mapped_column(String(120), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class VerificationLog(Base):
    """Immutable audit log of verification, merge, and opt-out decisions."""

    __tablename__ = "verification_logs"
    __table_args__ = {"schema": _SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    new_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    method: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class AuthenticationLog(Base):
    """Audit record for administrator sign-ins, denials, and sign-outs."""

    __tablename__ = "authentication_logs"
    __table_args__ = {"schema": _SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    administrator_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
