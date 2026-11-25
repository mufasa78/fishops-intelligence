"""
FishOps Prospecting & Relationship Intelligence – Streamlit dashboard.

Launch:
    streamlit run app.py
"""

from __future__ import annotations

import json
import time

import httpx
import pandas as pd
import streamlit as st
from supabase_auth.errors import AuthApiError
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from fishops.auth import (
    AuthenticatedSession,
    Administrator,
    SupabaseAuthConfigurationError,
    SupabaseAuthSessionError,
    UnauthorizedAdministratorError,
    UnconfirmedEmailError,
    get_authorized_administrator,
    get_invitation_browser_config,
    normalize_email,
    refresh_authenticated_session,
    sign_in_with_password,
    sign_out_session,
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

AUTH_SESSION_KEY = "fishops_auth_session"
LOGIN_EMAIL_KEY = "fishops_login_email"
LOGIN_PASSWORD_KEY = "fishops_login_password"

if st.session_state.pop("fishops_clear_login_password", False):
    st.session_state[LOGIN_PASSWORD_KEY] = ""


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


def _render_invitation_password_setup_bridge() -> None:
    """Handle Supabase's browser-only invite fragment without exposing it to Streamlit."""
    try:
        supabase_url, publishable_key, admin_emails = get_invitation_browser_config()
        config = {
            "url": supabase_url,
            "publishableKey": publishable_key,
            "adminEmails": admin_emails,
        }
    except SupabaseAuthConfigurationError:
        config = {"url": "", "publishableKey": "", "adminEmails": []}

    invitation_component = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body { margin: 0; color: #172b4d; font: 16px system-ui, sans-serif; }
    #panel { position: fixed; inset: 0; z-index: 2147483000; box-sizing: border-box; display: grid; min-height: 100vh; place-items: center; padding: 24px; background: #f3f6f9; }
    #panel[hidden] { display: none; }
    #card { box-sizing: border-box; width: min(100%, 520px); padding: 32px; border-radius: 12px; background: white; box-shadow: 0 8px 32px #0b254522; }
    h1 { margin-top: 0; color: #0b2545; font-size: 1.5rem; }
    p { color: #526174; line-height: 1.5; }
    label { display: block; margin: 16px 0 6px; font-weight: 600; }
    input { box-sizing: border-box; width: 100%; padding: 12px; border: 1px solid #aeb9c6; border-radius: 6px; font: inherit; }
    button { margin-top: 20px; padding: 12px 18px; border: 0; border-radius: 6px; background: #138b91; color: white; cursor: pointer; font: inherit; font-weight: 600; }
    button:disabled { cursor: wait; opacity: .7; }
    #message { margin-top: 16px; }
    #message[data-error="true"] { color: #a32121; }
  </style>
</head>
<body>
  <main id="panel" hidden>
    <section id="card">
      <h1>Complete your FishOps invitation</h1>
      <p id="account"></p>
      <p>Choose a password with at least 12 characters. Use a unique password you do not use elsewhere.</p>
      <form id="password-form" hidden>
        <label for="password">New password</label>
        <input id="password" type="password" minlength="12" autocomplete="new-password" required>
        <label for="confirm-password">Confirm new password</label>
        <input id="confirm-password" type="password" minlength="12" autocomplete="new-password" required>
        <button id="submit" type="submit">Set password</button>
      </form>
      <p id="message" role="status"></p>
      <button id="continue" type="button" hidden>Continue to sign in</button>
    </section>
  </main>
  <script>
    const config = __PUBLIC_CONFIG__;
    const panel = document.getElementById("panel");
    const account = document.getElementById("account");
    const message = document.getElementById("message");
    const form = document.getElementById("password-form");
    const submit = document.getElementById("submit");
    const continueButton = document.getElementById("continue");

    function hideBridge() {
      panel.hidden = true;
    }

    function showBridge() {
      panel.hidden = false;
    }

    function showError(text) {
      message.textContent = text;
      message.dataset.error = "true";
      continueButton.textContent = "Return to sign in";
      continueButton.hidden = false;
    }

    async function initializeInvitation(accessToken) {
      if (!config.url || !config.publishableKey) {
        showError("Invitation setup is not configured. Contact the system administrator.");
        return;
      }
      try {
        const response = await fetch(`${config.url}/auth/v1/user`, {
          headers: {
            apikey: config.publishableKey,
            Authorization: `Bearer ${accessToken}`
          }
        });
        if (!response.ok) {
          throw new Error("invalid-session");
        }
        const user = await response.json();
        const normalizedEmail = (user.email || "").trim().toLowerCase();
        const allowed = config.adminEmails.map(email => email.toLowerCase());
        if (!allowed.includes(normalizedEmail)) {
          showError("This invitation is not for an authorized FishOps administrator.");
          return;
        }
        account.textContent = `Set a password for ${normalizedEmail} to finish setup.`;
        form.hidden = false;
      } catch {
        showError("This invitation link is invalid or expired. Ask an administrator to send a new one.");
      }
    }

    try {
      const browserUrl = window.location;
      const hashParams = new URLSearchParams(browserUrl.hash.slice(1));
      if (hashParams.get("type") !== "invite") {
        hideBridge();
      } else {
        showBridge();
        const accessToken = hashParams.get("access_token");
        if (!accessToken) {
          showError("The invitation link is incomplete. Ask an administrator to send a new one.");
        } else {
          initializeInvitation(accessToken);
        }
      }
    } catch {
      hideBridge();
    }

    form.addEventListener("submit", async event => {
      event.preventDefault();
      message.textContent = "";
      message.dataset.error = "";
      const password = document.getElementById("password").value;
      const confirmation = document.getElementById("confirm-password").value;
      if (password.length < 12) {
        showError("Choose a password with at least 12 characters.");
        return;
      }
      if (password !== confirmation) {
        showError("The passwords do not match.");
        return;
      }
      submit.disabled = true;
      try {
        const hashParams = new URLSearchParams(window.location.hash.slice(1));
        const accessToken = hashParams.get("access_token");
        const response = await fetch(`${config.url}/auth/v1/user`, {
          method: "PUT",
          headers: {
            apikey: config.publishableKey,
            Authorization: `Bearer ${accessToken}`,
            "Content-Type": "application/json"
          },
          body: JSON.stringify({ password })
        });
        if (!response.ok) {
          throw new Error("password-update-failed");
        }
        form.hidden = true;
        message.dataset.error = "";
        message.textContent = "Password set. You can now sign in.";
        continueButton.textContent = "Continue to sign in";
        continueButton.hidden = false;
        window.history.replaceState(
          null,
          "",
          window.location.pathname + window.location.search
        );
      } catch {
        showError("Could not set the password. The invitation may have expired; request a new invitation if needed.");
      } finally {
        submit.disabled = false;
      }
    });

    continueButton.addEventListener("click", () => {
      window.history.replaceState(
        null,
        "",
        window.location.pathname + window.location.search
      );
      window.location.reload();
    });
  </script>
</body>
</html>
"""
    invitation_component = invitation_component.replace(
        "__PUBLIC_CONFIG__",
        json.dumps(config).replace("</", "<\\/"),
    )
    st.html(invitation_component, unsafe_allow_javascript=True)


def _render_login_page() -> None:
    _render_invitation_password_setup_bridge()
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
    denied_email = st.session_state.get("fishops_denied_email")
    if denied_email:
        st.title("Access denied")
        st.error("This email is not authorized to access FishOps Prospect Intelligence.")
        if st.button("Return to sign in"):
            st.session_state.pop("fishops_denied_email", None)
            st.rerun()
        st.stop()

    notice = st.session_state.pop("fishops_login_notice", None)
    if notice:
        st.warning(notice)
    error = st.session_state.pop("fishops_login_error", None)
    if error:
        st.error(error)

    with st.form("fishops_login_form"):
        email = st.text_input("Email", key=LOGIN_EMAIL_KEY, autocomplete="email")
        password = st.text_input(
            "Password",
            type="password",
            key=LOGIN_PASSWORD_KEY,
            autocomplete="current-password",
        )
        submitted = st.form_submit_button("Sign in", type="primary")

    st.caption("Sign-in is available only to approved FishOps administrators.")
    if not submitted:
        return

    normalized_email = normalize_email(email)
    administrator = get_authorized_administrator(normalized_email)
    if not normalized_email or not password:
        st.session_state["fishops_login_error"] = (
            "Enter both your administrator email and password."
        )
    elif administrator is None:
        _record_auth_event_or_warn(normalized_email, "login_denied")
        st.session_state["fishops_denied_email"] = normalized_email
    else:
        try:
            authenticated_session = sign_in_with_password(email, password)
        except UnauthorizedAdministratorError:
            _record_auth_event_or_warn(normalized_email, "login_denied")
            st.session_state["fishops_denied_email"] = normalized_email
        except UnconfirmedEmailError:
            _record_auth_event_or_warn(
                normalized_email, "login_failed", administrator.name
            )
            st.session_state["fishops_login_error"] = (
                "This account's email must be confirmed in Supabase before signing in."
            )
        except AuthApiError:
            _record_auth_event_or_warn(
                normalized_email, "login_failed", administrator.name
            )
            st.session_state["fishops_login_error"] = (
                "Sign-in failed. Check your email and password, then try again."
            )
        except httpx.HTTPError:
            _record_auth_event_or_warn(
                normalized_email, "login_failed", administrator.name
            )
            st.session_state["fishops_login_error"] = (
                "The authentication service is unavailable. Please try again later."
            )
        except SupabaseAuthConfigurationError:
            st.session_state["fishops_login_error"] = (
                "Authentication is not configured correctly. Contact the system administrator."
            )
        except SupabaseAuthSessionError:
            st.session_state["fishops_login_error"] = (
                "A valid authentication session could not be established. Please try again."
            )
        else:
            if not _record_auth_event(
                authenticated_session.email,
                "login_success",
                administrator.name,
            ):
                try:
                    sign_out_session(authenticated_session)
                except (AuthApiError, httpx.HTTPError):
                    st.session_state["fishops_login_notice"] = (
                        "The sign-in session could not be revoked; contact the system administrator."
                    )
                st.session_state["fishops_login_error"] = (
                    "Sign-in is unavailable because the login audit could not be written."
                )
            else:
                st.session_state[AUTH_SESSION_KEY] = authenticated_session
                st.session_state.pop("fishops_login_error", None)

    st.session_state["fishops_clear_login_password"] = True
    st.rerun()


def _resolve_active_administrator() -> tuple[AuthenticatedSession, Administrator] | None:
    authenticated_session = st.session_state.get(AUTH_SESSION_KEY)
    if not isinstance(authenticated_session, AuthenticatedSession):
        st.session_state.pop(AUTH_SESSION_KEY, None)
        return None

    if authenticated_session.expires_at <= int(time.time()) + 60:
        try:
            authenticated_session = refresh_authenticated_session(
                authenticated_session.refresh_token
            )
        except (
            AuthApiError,
            httpx.HTTPError,
            SupabaseAuthConfigurationError,
            SupabaseAuthSessionError,
            UnconfirmedEmailError,
        ):
            st.session_state.pop(AUTH_SESSION_KEY, None)
            st.session_state["fishops_login_notice"] = (
                "Your session could not be renewed. Please sign in again."
            )
            if not _record_auth_event(authenticated_session.email, "session_expired"):
                st.session_state["fishops_login_notice"] += (
                    " The session event could not be recorded."
                )
            return None
        st.session_state[AUTH_SESSION_KEY] = authenticated_session

    administrator = get_authorized_administrator(authenticated_session.email)
    if administrator is None:
        st.session_state.pop(AUTH_SESSION_KEY, None)
        _record_auth_event_or_warn(authenticated_session.email, "login_denied")
        st.session_state["fishops_denied_email"] = authenticated_session.email
        return None
    return authenticated_session, administrator


_active_auth = _resolve_active_administrator()
if _active_auth is None:
    _render_login_page()
    st.stop()

_authenticated_session, _administrator = _active_auth
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
    try:
        sign_out_session(_authenticated_session)
    except (AuthApiError, httpx.HTTPError):
        st.sidebar.warning(
            "The Supabase session could not be revoked, but local access is being cleared."
        )
    finally:
        st.session_state.pop(AUTH_SESSION_KEY, None)
        st.rerun()


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
