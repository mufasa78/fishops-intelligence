"""
FishOps Prospecting & Relationship Intelligence – Streamlit dashboard.

Launch:
    streamlit run app.py
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from fishops.auth import (
    Administrator,
    get_authenticated_administrator,
    is_auth0_configured,
    normalize_email,
)
from fishops.constants import (
    BUSINESS_TYPE_LABELS,
    PIPELINE_STAGE_LABELS,
    VERIFICATION_STATUSES,
)
from fishops.db.models import (
    AuthenticationLog,
    CollectionRun,
    Organization,
    SourceRecord,
)
from fishops.db.session import init_db, session_scope

st.set_page_config(
    page_title="FishOps Intelligence",
    page_icon="🐟",
    layout="wide",
    initial_sidebar_state="expanded",
)

AUTH_AUDIT_IDENTITY_KEY = "fishops_auth_audit_identity"
DENIED_IDENTITY_KEY = "fishops_denied_identity"
DENIED_EMAIL_KEY = "fishops_denied_email"


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

    df = _load_org_df()
    if df.empty:
        st.info("No organizations yet. Run the collector to populate the database.")
        st.stop()

    with st.expander("🔍 Filter", expanded=True):
        fcol1, fcol2, fcol3 = st.columns(3)
        with fcol1:
            type_opts = ["All"] + sorted(df["business_type"].unique().tolist())
            sel_type = st.selectbox("Business Type", type_opts)
        with fcol2:
            county_opts = ["All"] + sorted(df[df["county"] != ""]["county"].unique().tolist())
            sel_county = st.selectbox("County", county_opts)
        with fcol3:
            verification_opts = ["All"] + list(VERIFICATION_STATUSES)
            sel_ver = st.selectbox("Verification Status", verification_opts)

        search = st.text_input("Search name", placeholder="tilapia, Sagana, hatchery …")

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
        "business_name", "business_type", "county", "pipeline_stage",
        "verification_status", "outreach_status", "is_suppressed",
    ]
    st.dataframe(
        filtered[display_cols].rename(columns={
            "business_name": "Name",
            "business_type": "Type",
            "county": "County",
            "pipeline_stage": "Stage",
            "verification_status": "Verification",
            "outreach_status": "Status",
            "is_suppressed": "Suppressed",
        }),
        use_container_width=True,
        hide_index=True,
    )


# ── Page: Review Queue ───────────────────────────────────────────────────────

elif page == "🔍 Review Queue":
    st.title("🔍 Candidate Review Queue")
    st.caption(
        "Scraped records must be reviewed before the matched organization "
        "can progress past 'Needs Verification'.  "
        "Verification is recorded in the database; raw values are never overwritten."
    )

    df = _load_pending_records()
    if df.empty:
        st.success("No records pending review. 🎉")
        st.stop()

    st.metric("Pending records", len(df))

    display_cols = [
        "business_name", "type_hint", "phone", "phone_normalized",
        "email", "county", "source", "collected_at",
    ]
    st.dataframe(
        df[display_cols].rename(columns={
            "business_name": "Name",
            "type_hint": "Type Hint",
            "phone": "Phone (raw)",
            "phone_normalized": "Phone (normalized)",
            "email": "Email",
            "county": "County (inferred)",
            "source": "Source",
            "collected_at": "Collected",
        }),
        use_container_width=True,
        hide_index=True,
    )

    st.info(
        "Full review and approval UI (approve / merge / reject / opt-out) "
        "is delivered in Phase 4."
    )


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
    st.subheader("Collection Sources")
    source_data = {
        "Source": [
            "KEFS FAQs",
            "KEFS Hatchery Register",
            "Go Africa Online",
            "OpenStreetMap Overpass",
            "Wikidata SPARQL",
            "CSV Import",
        ],
        "Priority": ["Very High", "Very High", "High", "Supplementary", "Supplementary", "Manual"],
        "Adapter Key": ["kefs", "kefs", "goafrica", "osm", "wikidata", "--import-csv"],
        "Value Chain Coverage": [
            "Hatcheries, certified farms",
            "Registered aquaculture establishments",
            "Full value chain (52+ listings)",
            "Mapped farms and facilities",
            "Structured public business data",
            "Any external spreadsheet or register",
        ],
    }
    st.table(pd.DataFrame(source_data))

    st.markdown("---")
    st.subheader("Run Collector")
    st.code(
        "python collect.py --sources goafrica kefs osm wikidata --max-pages 5 --delay 3",
        language="bash",
    )
    st.code(
        "python collect.py --import-csv path/to/register.csv --source-name 'KEFS Manual'",
        language="bash",
    )

    st.info(
        "Collectors respect **robots.txt** and use a minimum 2-second delay.  "
        "Every record is tagged `unverified` until manually reviewed.  "
        "No automatically verified contacts are ever written to the database."
    )
