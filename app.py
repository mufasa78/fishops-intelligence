"""
FishOps Prospecting & Relationship Intelligence – Streamlit dashboard.

Launch:
    streamlit run app.py
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

import pandas as pd
import streamlit as st
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from fishops.collectors.businesslist import BusinessListFishMerchantsCollector
from fishops.collectors.csv_import import load_candidates_from_csv
from fishops.auth import (
    Administrator,
    get_authenticated_administrator,
    is_auth0_configured,
    normalize_email,
)
from fishops.constants import (
    BUSINESS_TYPES,
    BUSINESS_TYPE_LABELS,
    CONTACT_CHANNELS,
    LAWFUL_BASIS_OPTIONS,
    OUTREACH_STATUSES,
    PIPELINE_STAGES,
    PIPELINE_STAGE_LABELS,
    VERIFICATION_STATUSES,
)
from fishops.db.models import (
    AuthenticationLog,
    CollectionRun,
    ContactPoint,
    Organization,
    OutreachActivity,
    SourceRecord,
    VerificationLog,
)
from fishops.db.session import init_db, session_scope
from fishops.normalization import (
    normalize_business_name,
    normalize_email,
    normalize_phone,
    normalize_url,
)
from fishops.staging import stage_candidates

st.set_page_config(
    page_title="FishOps Intelligence",
    page_icon="🐟",
    layout="wide",
    initial_sidebar_state="expanded",
)

AUTH_AUDIT_IDENTITY_KEY = "fishops_auth_audit_identity"
DENIED_IDENTITY_KEY = "fishops_denied_identity"
DENIED_EMAIL_KEY = "fishops_denied_email"
EAST_AFRICA_TIME = timezone(timedelta(hours=3))


@st.cache_resource(show_spinner=False)
def _get_engine():
    return init_db()


def _database_engine():
    try:
        return _get_engine()
    except OperationalError:
        st.error(
            "The database is currently unavailable. Check the Supabase "
            "connection settings and try again."
        )
        st.stop()


def _record_auth_event(
    email: str, event_type: str, name: str | None = None
) -> bool:
    try:
        with session_scope(_get_engine()) as session:
            session.add(
                AuthenticationLog(
                    email=email,
                    administrator_name=name,
                    event_type=event_type,
                )
            )
    except OperationalError:
        return False
    return True


def _record_auth_event_or_warn(
    email: str, event_type: str, name: str | None = None
) -> None:
    if not _record_auth_event(email, event_type, name):
        st.session_state["fishops_login_notice"] = (
            "The authentication event could not be recorded because the database is unavailable."
        )


def _render_login_page() -> None:
    st.markdown(
        """
        <style>
        .fishops-login { max-width: 760px; margin: 8vh auto; text-align: center; }
        .fishops-login h1 { color: #0b2545; letter-spacing: .12em; }
        .fishops-login h3 { color: #138b91; font-weight: 500; }
        .fishops-login p { color: #526174; font-size: 1.05rem; }
        </style>
        <div class="fishops-login">
          <h1>FISHOPS</h1>
          <h3>Prospecting &amp; Relationship Intelligence</h3>
          <p>Kenya Aquaculture Value Chain</p>
          <p>Your central workspace for aquaculture market intelligence,
          business relationships and commercial opportunities.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.info("Internal access only · Authorized administrators only")

    notice = st.session_state.pop("fishops_login_notice", None)
    if notice:
        st.warning(notice)

    if st.user.is_logged_in:
        denied_email = st.session_state.get(DENIED_EMAIL_KEY)
        if denied_email:
            st.title("Access denied")
            st.error(
                "This email is not authorized to access FishOps Prospect Intelligence, "
                "or its Auth0 email address is not verified."
            )
        else:
            st.error(
                "FishOps could not record your sign-in. Access remains blocked until "
                "the authentication audit is available."
            )
        if st.button("Sign out"):
            st.session_state.pop(AUTH_AUDIT_IDENTITY_KEY, None)
            st.session_state.pop(DENIED_IDENTITY_KEY, None)
            st.session_state.pop(DENIED_EMAIL_KEY, None)
            st.logout()
        st.stop()

    st.caption("Sign-in is available only to approved FishOps administrators.")
    if st.button("Sign in with Auth0", type="primary"):
        st.login("auth0")


def _resolve_active_administrator() -> Administrator | None:
    if not st.user.is_logged_in:
        return None

    email_claim = st.user.get("email")
    email = email_claim if isinstance(email_claim, str) else None
    administrator = get_authenticated_administrator(
        email,
        st.user.get("email_verified"),
    )
    subject = st.user.get("sub")
    identity = subject if isinstance(subject, str) and subject else normalize_email(email)

    if administrator is None:
        if not email:
            st.session_state.pop(DENIED_EMAIL_KEY, None)
        if email and identity and st.session_state.get(DENIED_IDENTITY_KEY) != identity:
            _record_auth_event_or_warn(email, "login_denied")
            st.session_state[DENIED_IDENTITY_KEY] = identity
            st.session_state[DENIED_EMAIL_KEY] = email
        return None

    st.session_state.pop(DENIED_IDENTITY_KEY, None)
    st.session_state.pop(DENIED_EMAIL_KEY, None)
    if st.session_state.get(AUTH_AUDIT_IDENTITY_KEY) != identity:
        if not _record_auth_event(
            administrator.email,
            "login_success",
            administrator.name,
        ):
            st.session_state["fishops_login_notice"] = (
                "Sign-in is unavailable because the login audit could not be written."
            )
            return None
        st.session_state[AUTH_AUDIT_IDENTITY_KEY] = identity

    st.session_state.pop("fishops_login_notice", None)
    return administrator


if not is_auth0_configured():
    st.error(
        "Auth0 is not configured for Streamlit. Add the [auth] and [auth.auth0] "
        "settings from .streamlit/secrets.toml.example to your local Streamlit "
        "secrets or deployment secrets."
    )
    st.stop()


_administrator = _resolve_active_administrator()
if _administrator is None:
    _render_login_page()
    st.stop()

ENGINE = _database_engine()

# ── Sidebar navigation ───────────────────────────────────────────────────────

PAGES = ["📊 Overview", "📋 Directory", "🔍 Review Queue", "📂 Data Collection"]
page = st.sidebar.radio("Navigation", PAGES, label_visibility="collapsed")
st.sidebar.markdown("---")
st.sidebar.caption("FishOps Prospect Intelligence v0.1")
st.sidebar.caption("All scraped data is **unverified** until reviewed.")
st.sidebar.markdown("---")
st.sidebar.write(f"**{_administrator.name}**")
st.sidebar.caption(_administrator.email)
st.sidebar.caption(_administrator.role)

with st.sidebar.expander("Authentication history"):
    with session_scope(ENGINE) as session:
        last_login = session.execute(
            select(AuthenticationLog.created_at)
            .where(
                AuthenticationLog.email == _administrator.email,
                AuthenticationLog.event_type == "login_success",
            )
            .order_by(AuthenticationLog.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        auth_events = session.execute(
            select(AuthenticationLog)
            .order_by(AuthenticationLog.created_at.desc())
            .limit(50)
        ).scalars().all()
    st.caption(f"Last login: {last_login or 'Not recorded'}")
    st.dataframe(
        [
            {
                "Email": event.email,
                "Event": event.event_type,
                "Time": event.created_at,
            }
            for event in auth_events
        ],
        use_container_width=True,
        hide_index=True,
    )
if st.sidebar.button("Log out"):
    if not _record_auth_event(_administrator.email, "logout", _administrator.name):
        st.sidebar.warning("Logout could not be recorded, but you are being signed out.")
    st.session_state.pop(AUTH_AUDIT_IDENTITY_KEY, None)
    st.logout()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _load_org_df() -> pd.DataFrame:
    """Load all organizations as a flat DataFrame."""
    with session_scope(ENGINE) as session:
        rows = session.execute(select(Organization)).scalars().all()
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(
            [
                {
                    "id": o.id,
                    "business_name": o.business_name,
                    "business_type": BUSINESS_TYPE_LABELS.get(o.business_type, o.business_type),
                    "country_code": o.country_code,
                    "county": o.county or "",
                    "city_town": o.city_town or "",
                    "pipeline_stage": PIPELINE_STAGE_LABELS.get(o.pipeline_stage, o.pipeline_stage),
                    "verification_status": o.verification_status,
                    "outreach_status": o.outreach_status,
                    "is_suppressed": o.is_suppressed,
                    "website": o.website or "",
                    "created_at": o.created_at,
                }
                for o in rows
            ]
        )


def _load_pending_records() -> pd.DataFrame:
    """Load source records awaiting review."""
    with session_scope(ENGINE) as session:
        rows = session.execute(
            select(SourceRecord).where(SourceRecord.review_status == "pending").limit(500)
        ).scalars().all()
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(
            [
                {
                    "id": r.id,
                    "business_name": r.business_name_raw,
                    "type_hint": r.business_type_hint,
                    "phone": r.phone_raw or "",
                    "phone_normalized": r.phone_normalized or "",
                    "email": r.email_raw or "",
                    "county": r.county_inferred or "",
                    "source": r.source_name,
                    "source_url": r.source_url,
                    "collected_at": r.collected_at,
                    "review_status": r.review_status,
                }
                for r in rows
            ]
        )


def _load_collection_runs() -> pd.DataFrame:
    with session_scope(ENGINE) as session:
        rows = session.execute(
            select(CollectionRun).order_by(CollectionRun.started_at.desc()).limit(50)
        ).scalars().all()
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(
            [
                {
                    "id": r.id,
                    "adapter": r.adapter_name,
                    "started_at": r.started_at,
                    "finished_at": r.finished_at,
                    "status": r.status,
                    "found": r.items_found,
                    "new": r.items_new,
                    "duplicate": r.items_duplicate,
                }
                for r in rows
            ]
        )


def _count_orgs_by(session, column, status_filter=None) -> dict:
    q = session.execute(select(column, func.count()).group_by(column))
    return {row[0]: row[1] for row in q}


def _log_verification(
    session,
    entity_type: str,
    entity_id: int,
    action: str,
    actor: str,
    previous_status: str | None = None,
    new_status: str | None = None,
    method: str | None = None,
    notes: str | None = None,
) -> None:
    session.add(
        VerificationLog(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            previous_status=previous_status,
            new_status=new_status,
            actor=actor,
            method=method,
            notes=notes,
        )
    )


# ── Page: Overview ───────────────────────────────────────────────────────────

if page == "📊 Overview":
    st.title("🐟 FishOps Prospect Intelligence")
    st.caption("Kenya Aquaculture Value Chain · Relationship & Business Development CRM")

    df = _load_org_df()
    with session_scope(ENGINE) as s:
        total_orgs = s.execute(select(func.count()).select_from(Organization)).scalar() or 0
        total_verified = s.execute(
            select(func.count()).select_from(Organization)
            .where(Organization.verification_status == "verified")
        ).scalar() or 0
        total_pending = s.execute(
            select(func.count()).select_from(SourceRecord)
            .where(SourceRecord.review_status == "pending")
        ).scalar() or 0
        total_suppressed = s.execute(
            select(func.count()).select_from(Organization)
            .where(Organization.is_suppressed == True)
        ).scalar() or 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Businesses", total_orgs)
    c2.metric("Verified Prospects", total_verified)
    c3.metric("Pending Review", total_pending)
    c4.metric("Suppressed", total_suppressed)

    if not df.empty:
        st.markdown("---")
        col_left, col_right = st.columns(2)

        with col_left:
            st.subheader("Businesses by Type")
            type_counts = df["business_type"].value_counts().reset_index()
            type_counts.columns = ["Business Type", "Count"]
            st.bar_chart(type_counts.set_index("Business Type"))

        with col_right:
            st.subheader("Pipeline Stages")
            stage_counts = df["pipeline_stage"].value_counts().reset_index()
            stage_counts.columns = ["Stage", "Count"]
            st.bar_chart(stage_counts.set_index("Stage"))

        st.subheader("Businesses by County")
        county_counts = df[df["county"] != ""]["county"].value_counts().reset_index()
        if not county_counts.empty:
            county_counts.columns = ["County", "Count"]
            st.bar_chart(county_counts.set_index("County"))
        else:
            st.info("No county data yet — populate via collection and verification.")
    else:
        st.info(
            "No organizations in the database yet. "
            "Run `python collect.py` to populate, or use the **Data Collection** page."
        )


# ── Page: Directory ──────────────────────────────────────────────────────────

elif page == "📋 Directory":
    st.title("📋 Business Directory")

    with st.expander("➕ Add a business", expanded=False):
        with st.form("create_organization_form"):
            new_name = st.text_input("Business name")
            new_type = st.selectbox(
                "Business type",
                BUSINESS_TYPES,
                format_func=lambda value: BUSINESS_TYPE_LABELS.get(value, value),
            )
            new_county = st.text_input("County")
            new_city = st.text_input("City / town")
            new_address = st.text_input("Address")
            new_website = st.text_input("Website")
            create_business = st.form_submit_button("Create business")
        if create_business:
            normalized_name = normalize_business_name(new_name)
            if not new_name.strip():
                st.error("Business name is required.")
            elif not normalized_name:
                st.error("Enter a business name that can be normalized.")
            else:
                created_business_name = None
                with session_scope(ENGINE) as session:
                    existing = session.execute(
                        select(Organization).where(
                            Organization.normalized_name == normalized_name,
                            Organization.country_code == "KE",
                        )
                    ).scalar_one_or_none()
                    if existing:
                        st.error(
                            f"{existing.business_name} already exists in the directory."
                        )
                    else:
                        org = Organization(
                            business_name=new_name.strip(),
                            normalized_name=normalized_name,
                            business_type=new_type,
                            country_code="KE",
                            county=new_county.strip() or None,
                            city_town=new_city.strip() or None,
                            address_raw=new_address.strip() or None,
                            website=new_website.strip() or None,
                            pipeline_stage="discovered",
                            outreach_status="active",
                            verification_status="unverified",
                        )
                        session.add(org)
                        session.flush()
                        _log_verification(
                            session,
                            "organization",
                            org.id,
                            "created",
                            _administrator.email,
                            new_status="unverified",
                            notes="Created from the business directory.",
                        )
                        created_business_name = org.business_name
                if created_business_name:
                    st.success(f"Created {created_business_name}.")
                    st.rerun()

    df = _load_org_df()
    if df.empty:
        st.info("No organizations yet. Add a business or import a candidate first.")
    else:
        with st.expander("🔍 Filter", expanded=True):
            fcol1, fcol2, fcol3 = st.columns(3)
            with fcol1:
                type_opts = ["All"] + sorted(df["business_type"].unique().tolist())
                sel_type = st.selectbox("Business Type", type_opts)
            with fcol2:
                county_opts = ["All"] + sorted(
                    df[df["county"] != ""]["county"].unique().tolist()
                )
                sel_county = st.selectbox("County", county_opts)
            with fcol3:
                verification_opts = ["All"] + list(VERIFICATION_STATUSES)
                sel_ver = st.selectbox("Verification Status", verification_opts)

            search = st.text_input(
                "Search name", placeholder="tilapia, Sagana, hatchery …"
            )

        filtered = df.copy()
        if sel_type != "All":
            filtered = filtered[filtered["business_type"] == sel_type]
        if sel_county != "All":
            filtered = filtered[filtered["county"] == sel_county]
        if sel_ver != "All":
            filtered = filtered[filtered["verification_status"] == sel_ver]
        if search:
            mask = filtered["business_name"].str.contains(search, case=False, na=False)
            filtered = filtered[mask]

        st.caption(f"{len(filtered)} of {len(df)} organizations")
        display_cols = [
            "business_name",
            "business_type",
            "county",
            "pipeline_stage",
            "verification_status",
            "outreach_status",
            "is_suppressed",
        ]
        st.dataframe(
            filtered[display_cols].rename(
                columns={
                    "business_name": "Name",
                    "business_type": "Type",
                    "county": "County",
                    "pipeline_stage": "Stage",
                    "verification_status": "Verification",
                    "outreach_status": "Status",
                    "is_suppressed": "Suppressed",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    with session_scope(ENGINE) as session:
        organizations = session.execute(
            select(Organization).order_by(Organization.business_name)
        ).scalars().all()
    if not organizations:
        st.stop()

    st.markdown("---")
    st.subheader("Edit business and progress pipeline")
    organization_ids = [org.id for org in organizations]
    organizations_by_id = {org.id: org for org in organizations}
    selected_org_id = st.selectbox(
        "Business",
        organization_ids,
        format_func=lambda org_id: organizations_by_id[org_id].business_name,
        key="directory_organization",
    )
    selected_org = organizations_by_id[selected_org_id]
    if selected_org.is_suppressed:
        st.warning(
            "This business is suppressed from outreach. Review its suppression "
            "reason before taking any next steps."
        )

    with st.form("organization_details_form"):
        detail_col1, detail_col2 = st.columns(2)
        with detail_col1:
            edit_name = st.text_input("Business name", value=selected_org.business_name)
            edit_type = st.selectbox(
                "Business type",
                BUSINESS_TYPES,
                index=(
                    BUSINESS_TYPES.index(selected_org.business_type)
                    if selected_org.business_type in BUSINESS_TYPES
                    else BUSINESS_TYPES.index("unknown")
                ),
                format_func=lambda value: BUSINESS_TYPE_LABELS.get(value, value),
            )
            edit_county = st.text_input(
                "County", value=selected_org.county or ""
            )
            edit_city = st.text_input(
                "City / town", value=selected_org.city_town or ""
            )
            edit_address = st.text_input(
                "Address", value=selected_org.address_raw or ""
            )
            edit_website = st.text_input(
                "Website", value=selected_org.website or ""
            )
        with detail_col2:
            edit_verification = st.selectbox(
                "Verification status",
                VERIFICATION_STATUSES,
                index=VERIFICATION_STATUSES.index(
                    selected_org.verification_status
                )
                if selected_org.verification_status in VERIFICATION_STATUSES
                else 0,
            )
            edit_method = st.text_input(
                "Verification method",
                value=selected_org.verification_method or "",
                help="For example: called listed number, official register, or site visit.",
            )
            edit_verification_notes = st.text_area(
                "Verification notes", value=selected_org.verification_notes or ""
            )
            edit_stage = st.selectbox(
                "Pipeline stage",
                PIPELINE_STAGES,
                index=PIPELINE_STAGES.index(selected_org.pipeline_stage)
                if selected_org.pipeline_stage in PIPELINE_STAGES
                else 0,
                format_func=lambda value: PIPELINE_STAGE_LABELS.get(value, value),
            )
            edit_outreach_status = st.selectbox(
                "Outreach status",
                OUTREACH_STATUSES,
                index=OUTREACH_STATUSES.index(selected_org.outreach_status)
                if selected_org.outreach_status in OUTREACH_STATUSES
                else 0,
            )
            clear_suppression = (
                st.checkbox(
                    "Clear suppression after confirming the request is resolved",
                    value=False,
                )
                if selected_org.is_suppressed
                else False
            )
        edit_notes = st.text_area("Business notes", value=selected_org.notes or "")
        save_organization = st.form_submit_button("Save business")

    if save_organization:
        normalized_name = normalize_business_name(edit_name)
        if not normalized_name:
            st.error("Business name is required.")
        elif (
            edit_verification == "verified"
            and not edit_method.strip()
        ):
            st.error("Add a verification method before marking the business verified.")
        elif (
            edit_verification != "verified"
            and PIPELINE_STAGES.index(edit_stage)
            > PIPELINE_STAGES.index("needs_verification")
        ):
            st.error(
                "Verify the business before moving it beyond the Needs Verification stage."
            )
        elif edit_outreach_status == "do_not_contact" and clear_suppression:
            st.error("A do-not-contact business cannot have its suppression cleared.")
        else:
            organization_saved = False
            with session_scope(ENGINE) as session:
                org = session.get(Organization, selected_org_id)
                if org is None:
                    st.error("The selected business no longer exists.")
                else:
                    conflict = session.execute(
                        select(Organization).where(
                            Organization.normalized_name == normalized_name,
                            Organization.country_code == org.country_code,
                            Organization.id != org.id,
                        )
                    ).scalar_one_or_none()
                    if conflict:
                        st.error(
                            f"{conflict.business_name} already has the same normalized name."
                        )
                    else:
                        previous_status = org.verification_status
                        org.business_name = edit_name.strip()
                        org.normalized_name = normalized_name
                        org.business_type = edit_type
                        org.county = edit_county.strip() or None
                        org.city_town = edit_city.strip() or None
                        org.address_raw = edit_address.strip() or None
                        org.website = edit_website.strip() or None
                        org.verification_status = edit_verification
                        org.verification_method = edit_method.strip() or None
                        org.verification_notes = (
                            edit_verification_notes.strip() or None
                        )
                        org.pipeline_stage = edit_stage
                        org.outreach_status = edit_outreach_status
                        org.notes = edit_notes.strip() or None
                        if edit_outreach_status == "do_not_contact":
                            org.is_suppressed = True
                            org.suppressed_at = org.suppressed_at or datetime.now(
                                timezone.utc
                            )
                            org.suppression_reason = (
                                org.suppression_reason
                                or "Do not contact status set in the directory."
                            )
                        elif clear_suppression:
                            org.is_suppressed = False
                            org.suppressed_at = None
                            org.suppression_reason = None
                        if edit_verification == "verified":
                            org.verified_at = datetime.now(timezone.utc)
                            org.verified_by = _administrator.email
                        elif previous_status == "verified":
                            org.verified_at = None
                            org.verified_by = None
                        _log_verification(
                            session,
                            "organization",
                            org.id,
                            "directory_updated",
                            _administrator.email,
                            previous_status=previous_status,
                            new_status=edit_verification,
                            method=edit_method.strip() or None,
                            notes="Business details and pipeline fields updated.",
                        )
                        organization_saved = True
            if organization_saved:
                st.success("Business details saved.")
                st.rerun()

    with session_scope(ENGINE) as session:
        contact_rows = session.execute(
            select(ContactPoint)
            .where(ContactPoint.organization_id == selected_org_id)
            .order_by(ContactPoint.channel, ContactPoint.value_raw)
        ).scalars().all()
        contact_data = [
            {
                "id": contact.id,
                "channel": contact.channel,
                "value": contact.value_raw,
                "verification": contact.verification_status,
                "opted_out": contact.is_opted_out,
                "source_record_id": contact.source_record_id,
            }
            for contact in contact_rows
        ]

    st.markdown("---")
    st.subheader("Contact details")
    if contact_data:
        st.dataframe(
            [
                {
                    "Channel": CONTACT_CHANNELS[
                        CONTACT_CHANNELS.index(row["channel"])
                    ]
                    if row["channel"] in CONTACT_CHANNELS
                    else row["channel"],
                    "Value": row["value"],
                    "Verification": row["verification"],
                    "Opted out": row["opted_out"],
                    "Source record": row["source_record_id"] or "",
                }
                for row in contact_data
            ],
            use_container_width=True,
            hide_index=True,
        )

    with st.expander("➕ Add contact detail", expanded=False):
        with st.form("create_contact_form"):
            contact_channel = st.selectbox("Channel", CONTACT_CHANNELS)
            contact_value = st.text_input("Phone, email, website, or profile")
            contact_label = st.text_input("Label (optional)")
            contact_lawful_basis = st.selectbox(
                "Lawful basis", LAWFUL_BASIS_OPTIONS
            )
            create_contact = st.form_submit_button("Add contact")
        if create_contact:
            if not contact_value.strip():
                st.error("Contact value is required.")
            else:
                contact_created = False
                with session_scope(ENGINE) as session:
                    existing_contact = session.execute(
                        select(ContactPoint).where(
                            ContactPoint.organization_id == selected_org_id,
                            ContactPoint.channel == contact_channel,
                            ContactPoint.value_raw == contact_value.strip(),
                        )
                    ).scalar_one_or_none()
                    if existing_contact:
                        st.error("This contact detail is already attached to the business.")
                    else:
                        contact = ContactPoint(
                            organization_id=selected_org_id,
                            channel=contact_channel,
                            value_raw=contact_value.strip(),
                            value_normalized=(
                                normalize_phone(contact_value, selected_org.country_code)
                                if contact_channel == "phone"
                                else normalize_email(contact_value)
                                if contact_channel == "email"
                                else normalize_url(contact_value)
                                if contact_channel in ("website", "social")
                                else None
                            ),
                            label=contact_label.strip() or None,
                            verification_status="unverified",
                            lawful_basis=contact_lawful_basis,
                            is_opted_out=False,
                        )
                        session.add(contact)
                        session.flush()
                        _log_verification(
                            session,
                            "contact_point",
                            contact.id,
                            "created",
                            _administrator.email,
                            new_status="unverified",
                            notes="Contact detail added from the directory.",
                        )
                        contact_created = True
                if contact_created:
                    st.success("Contact detail added as unverified.")
                    st.rerun()

    if contact_data:
        contact_ids = [row["id"] for row in contact_data]
        contacts_by_id = {row["id"]: row for row in contact_data}
        selected_contact_id = st.selectbox(
            "Edit contact detail",
            contact_ids,
            format_func=lambda contact_id: (
                f'{contacts_by_id[contact_id]["channel"]}: '
                f'{contacts_by_id[contact_id]["value"]}'
            ),
        )
        with session_scope(ENGINE) as session:
            contact = session.get(ContactPoint, selected_contact_id)
            contact_values = {
                "channel": contact.channel,
                "value": contact.value_raw,
                "label": contact.label or "",
                "verification_status": contact.verification_status,
                "verification_method": contact.verification_method or "",
                "lawful_basis": contact.lawful_basis,
                "is_opted_out": contact.is_opted_out,
                "opt_out_reason": contact.opt_out_reason or "",
            }
        with st.form("edit_contact_form"):
            edit_contact_channel = st.selectbox(
                "Channel",
                CONTACT_CHANNELS,
                index=CONTACT_CHANNELS.index(contact_values["channel"])
                if contact_values["channel"] in CONTACT_CHANNELS
                else 0,
            )
            edit_contact_value = st.text_input(
                "Value", value=contact_values["value"]
            )
            edit_contact_label = st.text_input(
                "Label", value=contact_values["label"]
            )
            edit_contact_status = st.selectbox(
                "Contact verification",
                VERIFICATION_STATUSES,
                index=VERIFICATION_STATUSES.index(
                    contact_values["verification_status"]
                )
                if contact_values["verification_status"] in VERIFICATION_STATUSES
                else 0,
            )
            edit_contact_method = st.text_input(
                "Contact verification method",
                value=contact_values["verification_method"],
            )
            edit_contact_basis = st.selectbox(
                "Lawful basis",
                LAWFUL_BASIS_OPTIONS,
                index=(
                    LAWFUL_BASIS_OPTIONS.index(contact_values["lawful_basis"])
                    if contact_values["lawful_basis"] in LAWFUL_BASIS_OPTIONS
                    else 0
                ),
            )
            edit_contact_opted_out = st.checkbox(
                "Do not contact this address/number",
                value=contact_values["is_opted_out"],
            )
            edit_contact_opt_out_reason = st.text_input(
                "Opt-out reason", value=contact_values["opt_out_reason"]
            )
            save_contact = st.form_submit_button("Save contact detail")
        if save_contact:
            if not edit_contact_value.strip():
                st.error("Contact value is required.")
            elif (
                edit_contact_status == "verified"
                and not edit_contact_method.strip()
            ):
                st.error("Add a verification method before verifying this contact.")
            else:
                contact_saved = False
                with session_scope(ENGINE) as session:
                    contact = session.get(ContactPoint, selected_contact_id)
                    if contact is None:
                        st.error("The selected contact no longer exists.")
                    else:
                        previous_status = contact.verification_status
                        contact.channel = edit_contact_channel
                        contact.value_raw = edit_contact_value.strip()
                        contact.value_normalized = (
                            normalize_phone(
                                edit_contact_value, selected_org.country_code
                            )
                            if edit_contact_channel == "phone"
                            else normalize_email(edit_contact_value)
                            if edit_contact_channel == "email"
                            else normalize_url(edit_contact_value)
                            if edit_contact_channel in ("website", "social")
                            else None
                        ) or None
                        contact.label = edit_contact_label.strip() or None
                        contact.verification_status = edit_contact_status
                        contact.verification_method = (
                            edit_contact_method.strip() or None
                        )
                        contact.lawful_basis = edit_contact_basis
                        contact.is_opted_out = edit_contact_opted_out
                        contact.opted_out_at = (
                            datetime.now(timezone.utc)
                            if edit_contact_opted_out
                            else None
                        )
                        contact.opt_out_reason = (
                            edit_contact_opt_out_reason.strip() or None
                        )
                        if edit_contact_status == "verified":
                            contact.verified_at = datetime.now(timezone.utc)
                            contact.verified_by = _administrator.email
                        elif previous_status == "verified":
                            contact.verified_at = None
                            contact.verified_by = None
                        _log_verification(
                            session,
                            "contact_point",
                            contact.id,
                            "contact_updated",
                            _administrator.email,
                            previous_status=previous_status,
                            new_status=edit_contact_status,
                            method=edit_contact_method.strip() or None,
                            notes=(
                                "Contact detail updated; opted out."
                                if edit_contact_opted_out
                                else "Contact detail updated."
                            ),
                        )
                        contact_saved = True
                if contact_saved:
                    st.success("Contact detail saved.")
                    st.rerun()

    st.markdown("---")
    st.subheader("Outreach and next steps")
    with st.form("outreach_activity_form"):
        available_contact_ids = [None] + [row["id"] for row in contact_data]
        contact_labels = {
            row["id"]: f'{row["channel"]}: {row["value"]}' for row in contact_data
        }
        outreach_contact_id = st.selectbox(
            "Contact used",
            available_contact_ids,
            format_func=lambda contact_id: (
                "Not linked"
                if contact_id is None
                else contact_labels[contact_id]
            ),
        )
        activity_type = st.selectbox(
            "Activity type",
            ("call", "email", "whatsapp", "meeting", "site_visit", "note", "other"),
        )
        activity_outcome = st.text_input(
            "Outcome", placeholder="e.g. spoke with manager; call back requested"
        )
        activity_notes = st.text_area("Activity notes")
        next_step = st.text_input("Next step (optional)")
        due_date = st.date_input(
            "Next step due date (East Africa Time)",
            value=datetime.now(EAST_AFRICA_TIME).date(),
        )
        due_time = st.time_input("Next step due time", value=time(9, 0))
        save_activity = st.form_submit_button("Log activity")
    if save_activity:
        if next_step.strip():
            due_at = datetime.combine(
                due_date, due_time, tzinfo=EAST_AFRICA_TIME
            )
        else:
            due_at = None
        with session_scope(ENGINE) as session:
            session.add(
                OutreachActivity(
                    organization_id=selected_org_id,
                    contact_point_id=outreach_contact_id,
                    activity_type=activity_type,
                    outcome=activity_outcome.strip() or None,
                    notes=activity_notes.strip() or None,
                    next_step=next_step.strip() or None,
                    next_step_due_at=due_at,
                    actor=_administrator.email,
                )
            )
        st.success("Activity logged.")
        st.rerun()

    with session_scope(ENGINE) as session:
        activities = session.execute(
            select(OutreachActivity)
            .where(OutreachActivity.organization_id == selected_org_id)
            .order_by(OutreachActivity.created_at.desc())
        ).scalars().all()
    if activities:
        st.dataframe(
            [
                {
                    "Activity": activity.activity_type,
                    "Outcome": activity.outcome or "",
                    "Notes": activity.notes or "",
                    "Next step": activity.next_step or "",
                    "Due": activity.next_step_due_at or "",
                    "Logged": activity.created_at,
                    "By": activity.actor,
                }
                for activity in activities
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No outreach activity has been logged for this business.")


# ── Page: Review Queue ───────────────────────────────────────────────────────

elif page == "🔍 Review Queue":
    st.title("🔍 Candidate Review Queue")
    st.caption(
        "Review public-source records, correct missing details, and link them to "
        "the right business. Approval does not automatically verify a business or contact."
    )

    df = _load_pending_records()
    if df.empty:
        st.success("No records pending review. 🎉")
    else:
        st.metric("Pending records", len(df))
        display_cols = [
            "id",
            "business_name",
            "type_hint",
            "phone",
            "phone_normalized",
            "email",
            "county",
            "source",
            "collected_at",
        ]
        st.dataframe(
            df[display_cols].rename(
                columns={
                    "id": "Record",
                    "business_name": "Name",
                    "type_hint": "Type Hint",
                    "phone": "Phone (raw)",
                    "phone_normalized": "Phone (normalized)",
                    "email": "Email",
                    "county": "County (inferred)",
                    "source": "Source",
                    "collected_at": "Collected",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )
        record_ids = df["id"].astype(int).tolist()
        record_names = {
            int(row["id"]): f'{row["business_name"]} — {row["source"]}'
            for _, row in df.iterrows()
        }
        selected_record_id = st.selectbox(
            "Candidate to review",
            record_ids,
            format_func=lambda record_id: (
                f'{record_id}: {record_names[record_id]}'
            ),
        )
        with session_scope(ENGINE) as session:
            source_record = session.get(SourceRecord, selected_record_id)
            candidate_values = {
                "business_name": source_record.business_name_raw,
                "business_type": source_record.business_type_hint,
                "phone": source_record.phone_raw or "",
                "email": source_record.email_raw or "",
                "website": source_record.website_raw or "",
                "county": source_record.county_inferred or "",
                "location": source_record.location_text_raw or "",
                "latitude": source_record.latitude,
                "longitude": source_record.longitude,
                "source_url": source_record.source_url,
                "matched_organization_id": source_record.matched_organization_id,
                "raw_payload": source_record.raw_payload_json,
            }
            organizations = session.execute(
                select(Organization).order_by(Organization.business_name)
            ).scalars().all()
        st.caption(f"Source: {candidate_values['source_url']}")
        if candidate_values["raw_payload"]:
            with st.expander("Original source payload"):
                st.code(candidate_values["raw_payload"], language="json")

        org_ids = [org.id for org in organizations]
        orgs_by_id = {org.id: org for org in organizations}
        org_choices: list[int] = [0] + org_ids
        matched_id = candidate_values["matched_organization_id"]
        default_org_index = (
            org_choices.index(matched_id) if matched_id in org_choices else 0
        )
        with st.form("review_candidate_form"):
            review_col1, review_col2 = st.columns(2)
            with review_col1:
                review_name = st.text_input(
                    "Business name", value=candidate_values["business_name"]
                )
                review_type = st.selectbox(
                    "Business type",
                    BUSINESS_TYPES,
                    index=BUSINESS_TYPES.index(candidate_values["business_type"])
                    if candidate_values["business_type"] in BUSINESS_TYPES
                    else BUSINESS_TYPES.index("unknown"),
                    format_func=lambda value: BUSINESS_TYPE_LABELS.get(value, value),
                )
                review_phone = st.text_input(
                    "Phone", value=candidate_values["phone"]
                )
                review_email = st.text_input(
                    "Email", value=candidate_values["email"]
                )
                review_website = st.text_input(
                    "Website", value=candidate_values["website"]
                )
            with review_col2:
                review_county = st.text_input(
                    "County", value=candidate_values["county"]
                )
                review_location = st.text_input(
                    "Address / location", value=candidate_values["location"]
                )
                review_latitude = st.text_input(
                    "Latitude",
                    value=(
                        str(candidate_values["latitude"])
                        if candidate_values["latitude"] is not None
                        else ""
                    ),
                )
                review_longitude = st.text_input(
                    "Longitude",
                    value=(
                        str(candidate_values["longitude"])
                        if candidate_values["longitude"] is not None
                        else ""
                    ),
                )
                review_action = st.selectbox(
                    "Review decision",
                    (
                        "approve",
                        "merge",
                        "duplicate",
                        "reject",
                    ),
                    format_func=lambda value: {
                        "approve": "Approve candidate",
                        "merge": "Link to selected business",
                        "duplicate": "Mark as duplicate",
                        "reject": "Reject as noise",
                    }[value],
                )
                review_target_id = st.selectbox(
                    "Link to business (or create a new shell)",
                    org_choices,
                    index=default_org_index,
                    format_func=lambda org_id: (
                        "Create a new business shell"
                        if org_id == 0
                        else orgs_by_id[org_id].business_name
                    ),
                )
            review_notes = st.text_area("Review notes")
            submit_review = st.form_submit_button("Save review")

        if submit_review:
            if not review_name.strip():
                st.error("Business name is required.")
            elif review_action == "merge" and review_target_id == 0:
                st.error("Choose an existing business to link this candidate.")
            else:
                coordinates_valid = False
                try:
                    latitude = (
                        float(review_latitude.strip())
                        if review_latitude.strip()
                        else None
                    )
                    longitude = (
                        float(review_longitude.strip())
                        if review_longitude.strip()
                        else None
                    )
                except ValueError:
                    st.error("Latitude and longitude must be numeric.")
                else:
                    coordinates_valid = True
                    if latitude is not None and not -90 <= latitude <= 90:
                        st.error("Latitude must be between -90 and 90.")
                        coordinates_valid = False
                    elif longitude is not None and not -180 <= longitude <= 180:
                        st.error("Longitude must be between -180 and 180.")
                        coordinates_valid = False
                if coordinates_valid:
                    review_saved = False
                    with session_scope(ENGINE) as session:
                        record = session.get(SourceRecord, selected_record_id)
                        if record is None or record.review_status != "pending":
                            st.error("This candidate has already been reviewed.")
                        else:
                            org = (
                                session.get(Organization, review_target_id)
                                if review_target_id
                                else None
                            )
                            if review_action == "merge" and org is None:
                                st.error("The selected business no longer exists.")
                            else:
                                if review_action in ("approve", "merge"):
                                    if org is None:
                                        normalized_name = normalize_business_name(
                                            review_name
                                        )
                                        org = session.execute(
                                            select(Organization).where(
                                                Organization.normalized_name
                                                == normalized_name,
                                                Organization.country_code
                                                == record.country_code,
                                            )
                                        ).scalar_one_or_none()
                                        if org is None:
                                            org = Organization(
                                                business_name=review_name.strip(),
                                                normalized_name=normalized_name,
                                                business_type=review_type,
                                                country_code=record.country_code,
                                                pipeline_stage="discovered",
                                                outreach_status="active",
                                                verification_status="unverified",
                                            )
                                            session.add(org)
                                            session.flush()
                                    if org.verification_status != "verified":
                                        org.business_name = review_name.strip()
                                        org.normalized_name = normalize_business_name(
                                            review_name
                                        )
                                        org.business_type = review_type
                                        org.county = review_county.strip() or None
                                        org.address_raw = (
                                            review_location.strip() or None
                                        )
                                        org.latitude = latitude
                                        org.longitude = longitude
                                        org.website = review_website.strip() or None
                                    record.matched_organization_id = org.id
                                    contact_values = (
                                        ("phone", review_phone.strip()),
                                        ("email", review_email.strip()),
                                        ("website", review_website.strip()),
                                    )
                                    for channel, value in contact_values:
                                        if not value:
                                            continue
                                        existing_contact = session.execute(
                                            select(ContactPoint).where(
                                                ContactPoint.organization_id
                                                == org.id,
                                                ContactPoint.channel == channel,
                                                ContactPoint.value_raw == value,
                                            )
                                        ).scalar_one_or_none()
                                        if existing_contact is None:
                                            session.add(
                                                ContactPoint(
                                                    organization_id=org.id,
                                                    source_record_id=record.id,
                                                    channel=channel,
                                                    value_raw=value,
                                                    value_normalized=(
                                                        normalize_phone(
                                                            value, record.country_code
                                                        )
                                                        if channel == "phone"
                                                        else normalize_email(value)
                                                        if channel == "email"
                                                        else normalize_url(value)
                                                        if channel == "website"
                                                        else None
                                                    )
                                                    or None,
                                                    verification_status="unverified",
                                                    lawful_basis="unknown",
                                                    is_opted_out=False,
                                                )
                                            )
                                    review_status = (
                                        "approved_new"
                                        if review_action == "approve"
                                        else "merged_existing"
                                    )
                                elif review_action == "duplicate":
                                    review_status = "duplicate"
                                else:
                                    review_status = "rejected_noise"
                                record.review_status = review_status
                                record.reviewed_by = _administrator.email
                                record.reviewed_at = datetime.now(timezone.utc)
                                record.review_notes = review_notes.strip() or None
                                _log_verification(
                                    session,
                                    "source_record",
                                    record.id,
                                    f"review_{review_status}",
                                    _administrator.email,
                                    previous_status="pending",
                                    new_status=review_status,
                                    notes=review_notes.strip() or None,
                                )
                                review_saved = True
                    if review_saved:
                        st.success(
                            "Review saved. Any business/contact values remain "
                            "unverified until separately confirmed."
                        )
                        st.rerun()


# ── Page: Data Collection ────────────────────────────────────────────────────

elif page == "📂 Data Collection":
    st.title("📂 Data Collection & Source Management")

    runs_df = _load_collection_runs()
    if runs_df.empty:
        st.info(
            "No collection runs recorded. "
            "Run `python collect.py --sources goafrica kefs osm wikidata` to start."
        )
    else:
        st.subheader("Recent Collection Runs")
        st.dataframe(
            runs_df.rename(columns={
                "id": "Run",
                "adapter": "Adapter",
                "started_at": "Started",
                "finished_at": "Finished",
                "status": "Status",
                "found": "Found",
                "new": "New",
                "duplicate": "Duplicates",
            }),
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("---")
    st.subheader("Import a business register")
    st.caption(
        "Upload a CSV, inspect the parsed rows, then explicitly stage them. "
        "Importing creates unverified candidate and contact records; it does not "
        "send messages or verify phone numbers."
    )
    uploaded_csv = st.file_uploader(
        "Choose a CSV file", type=["csv"], key="fisheries_csv_upload"
    )
    if uploaded_csv is not None:
        import_source_name = st.text_input(
            "Source name",
            value=f"CSV import: {uploaded_csv.name}",
            key="csv_source_name",
        )
        import_source_url = st.text_input(
            "Source URL (optional)",
            key="csv_source_url",
        )
        csv_candidates = []
        csv_parse_failed = False
        try:
            csv_candidates = load_candidates_from_csv(
                uploaded_csv,
                source_name=import_source_name,
                source_url=import_source_url,
            )
        except (ValueError, UnicodeDecodeError) as exc:
            csv_parse_failed = True
            st.error(f"Could not parse uploaded CSV: {exc}")
        if not csv_parse_failed:
            st.write(f"Parsed {len(csv_candidates)} candidate rows.")
        if csv_candidates:
            st.dataframe(
                [
                    {
                        "Business": candidate.business_name,
                        "Phone": candidate.phone_raw,
                        "Email": candidate.email_raw,
                        "Website": candidate.website_raw,
                        "County": candidate.county_inferred,
                        "City / town": candidate.city_town,
                        "Address": candidate.address_raw,
                    }
                    for candidate in csv_candidates
                ],
                use_container_width=True,
                hide_index=True,
            )
            if st.button(
                f"Stage {len(csv_candidates)} candidates",
                type="primary",
                key="stage_uploaded_csv",
            ):
                with session_scope(ENGINE) as session:
                    result = stage_candidates(
                        session,
                        csv_candidates,
                        adapter_name="csv_import",
                        csv_path=uploaded_csv.name,
                    )
                st.success(
                    f"Staged {result['new']} new records; "
                    f"{result['duplicate']} duplicates; {result['errors']} errors."
                )
                st.rerun()
        elif not csv_parse_failed:
            st.warning("No rows with a business name were found.")

    st.markdown("---")
    st.subheader("Fetch public fish-merchant listings")
    st.caption(
        "Fetches only the publicly visible BusinessList fish-merchants category "
        "page. Review the results before staging. Paid directory exports and "
        "automated outreach are not used."
    )
    if st.button("Fetch BusinessList public listings", key="fetch_businesslist"):
        import requests

        st.session_state.pop("businesslist_candidates", None)
        try:
            with st.spinner("Fetching the public listing page..."):
                st.session_state["businesslist_candidates"] = (
                    BusinessListFishMerchantsCollector().collect()
                )
        except (requests.RequestException, PermissionError, ValueError) as exc:
            st.error(f"Could not fetch BusinessList listings: {exc}")
        else:
            st.success(
                f"Found {len(st.session_state['businesslist_candidates'])} "
                "public listings. No data has been staged yet."
            )

    businesslist_candidates = st.session_state.get("businesslist_candidates", [])
    if businesslist_candidates:
        st.dataframe(
            [
                {
                    "Business": candidate.business_name,
                    "Phone": candidate.phone_raw,
                    "Address": candidate.address_raw,
                    "Profile": candidate.profile_url,
                }
                for candidate in businesslist_candidates
            ],
            use_container_width=True,
            hide_index=True,
        )
        if st.button(
            f"Stage {len(businesslist_candidates)} BusinessList candidates",
            type="primary",
            key="stage_businesslist",
        ):
            with session_scope(ENGINE) as session:
                result = stage_candidates(
                    session,
                    businesslist_candidates,
                    adapter_name="businesslist_fish_merchants",
                )
            st.success(
                f"Staged {result['new']} new records; "
                f"{result['duplicate']} duplicates; {result['errors']} errors."
            )
            st.session_state.pop("businesslist_candidates", None)
            st.rerun()

    st.markdown("---")
    st.subheader("Collection Sources")
    source_data = {
        "Source": [
            "KEFS FAQs",
            "KEFS Hatchery Register",
            "Go Africa Online",
            "OpenStreetMap Overpass",
            "Wikidata SPARQL",
            "CSV Import",
            "BusinessList fish merchants",
        ],
        "Priority": [
            "Very High",
            "Very High",
            "High",
            "Supplementary",
            "Supplementary",
            "Manual",
            "Public listings",
        ],
        "Adapter Key": [
            "kefs",
            "kefs",
            "goafrica",
            "osm",
            "wikidata",
            "upload CSV",
            "businesslist",
        ],
        "Value Chain Coverage": [
            "Hatcheries, certified farms",
            "Registered aquaculture establishments",
            "Full value chain (52+ listings)",
            "Mapped farms and facilities",
            "Structured public business data",
            "Any external spreadsheet or register",
            "Public fish merchant listings and visible phone numbers",
        ],
    }
    st.table(pd.DataFrame(source_data))

    st.info(
        "Collectors respect **robots.txt**. Every collected organization and "
        "contact remains unverified until manually confirmed. Outreach is logged "
        "for human follow-up only; the app never sends messages automatically."
    )
