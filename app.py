"""
Digbi Health — Group Coaching Dashboard
Zoom Webinars API · Streamlit Cloud
"""

import os
import time
import urllib.parse
import requests
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta, date, timezone
from zoneinfo import ZoneInfo

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Digbi Group Coaching",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Zoom credentials from Streamlit secrets ──────────────────────────────────
CLIENT_ID     = st.secrets["ZOOM_CLIENT_ID"]
CLIENT_SECRET = st.secrets["ZOOM_CLIENT_SECRET"]
REDIRECT_URI  = st.secrets["ZOOM_REDIRECT_URI"]
ZOOM_API_BASE = "https://api.zoom.us/v2"

# ── The 7 recurring Group Coaching series (exact Zoom titles) ─────────────────
COACHING_SERIES = [
    "Digbi Health Orientation & How to Eat Smart - Group Coaching for Members",
    "Digbi Health Orientation & How to Eat Smart - Join Our Group Coaching Session",
    "Learn to Read and Apply Your Genetics Nutrition and Gut Monitoring Reports for Better Health",
    "Follow Your Gut Instincts: Understanding Your Gut Microbiome Report",
    "Introducing Digbi Health: An Exclusive Wellness Benefit with access to GLP-1s",
    "Fine Tuning (2-4.99% WL)",
    "Thriving with IBS",
]

SERIES_COLORS = {
    "Digbi Health Orientation & How to Eat Smart - Group Coaching for Members": "#1f77b4",
    "Digbi Health Orientation & How to Eat Smart - Join Our Group Coaching Session": "#ff7f0e",
    "Learn to Read and Apply Your Genetics Nutrition and Gut Monitoring Reports for Better Health": "#2ca02c",
    "Follow Your Gut Instincts: Understanding Your Gut Microbiome Report": "#d62728",
    "Introducing Digbi Health: An Exclusive Wellness Benefit with access to GLP-1s": "#9467bd",
    "Fine Tuning (2-4.99% WL)": "#8c564b",
    "Thriving with IBS": "#e377c2",
    "Other": "#7f7f7f",
}

# ── Hardcoded exclusion keywords (company-specific webinars to skip) ───────────
# Matched as substrings, case-insensitive.  Secrets-based EXCLUDED_KEYWORDS merged at runtime.

def _build_exclusion_list() -> list:
    """Load exclusion keywords from Streamlit secrets only (kept out of source code)."""
    raw = st.secrets.get("EXCLUDED_KEYWORDS", [])
    if isinstance(raw, str):
        return [k.strip().lower() for k in raw.split(",") if k.strip()]
    if isinstance(raw, list):
        return [str(k).strip().lower() for k in raw if k]
    return []


def map_to_series(topic: str) -> str:
    """Map a raw webinar topic to one of the 7 coaching series.

    Steps:
      1. Exclude company-specific webinars → "Other"
      2. Try exact-match table from secrets
      3. Fuzzy keyword fallback
    """
    if not isinstance(topic, str):
        return "Other"

    clean_topic = topic.strip()
    t = clean_topic.lower()

    # 1. EXCLUSION CHECK — runs before any series matching
    excluded_keywords = _build_exclusion_list()
    if any(keyword in t for keyword in excluded_keywords):
        return "Other"

    # 2. EXACT MATCHES (from secrets)
    raw_exact = st.secrets.get("EXACT_MATCHES", {})
    if isinstance(raw_exact, dict):
        exact_matches = {}
        for k in raw_exact.keys():
            k_lower = str(k).strip().lower()
            proper_case = str(k)
            for series_name in COACHING_SERIES:
                if series_name.lower() == k_lower:
                    proper_case = series_name
                    break
            exact_matches[k_lower] = proper_case
        if t in exact_matches:
            return exact_matches[t]

    # 3. FUZZY LOGIC FALLBACK
    # Orientation / Eat Smart — Solera / Gut-Only variant
    if "solera" in t and ("orientation" in t or "eat smart" in t or "gut only" in t):
        return "Digbi Health Orientation & How to Eat Smart - Join Our Group Coaching Session"
    if "gut only" in t and ("orientation" in t or "eat smart" in t):
        return "Digbi Health Orientation & How to Eat Smart - Join Our Group Coaching Session"
    # Orientation / Eat Smart — Employer / Full-product variant
    if ("orientation" in t or "eat smart" in t) and ("employer" in t or "full product" in t):
        return "Digbi Health Orientation & How to Eat Smart - Group Coaching for Members"
    # Exact title keyword anchors
    if "digbi health orientation" in t and "group coaching for members" in t:
        return "Digbi Health Orientation & How to Eat Smart - Group Coaching for Members"
    if "digbi health orientation" in t and "join our group coaching" in t:
        return "Digbi Health Orientation & How to Eat Smart - Join Our Group Coaching Session"
    if "orientation" in t and "eat smart" in t:
        return "Digbi Health Orientation & How to Eat Smart - Group Coaching for Members"
    # Gene + Gut kit
    if "gene" in t and "gut" in t:
        return "Learn to Read and Apply Your Genetics Nutrition and Gut Monitoring Reports for Better Health"
    if "genetics" in t and ("nutrition" in t or "gut monitoring" in t):
        return "Learn to Read and Apply Your Genetics Nutrition and Gut Monitoring Reports for Better Health"
    # Gut microbiome report
    if "gut instincts" in t or "microbiome" in t:
        return "Follow Your Gut Instincts: Understanding Your Gut Microbiome Report"
    if "gut kit" in t or ("read" in t and "gut" in t):
        return "Follow Your Gut Instincts: Understanding Your Gut Microbiome Report"
    # GLP-1 — generic only (company-specific already excluded above)
    if "glp" in t or "glp-1" in t or "semaglutide" in t or "ozempic" in t:
        return "Introducing Digbi Health: An Exclusive Wellness Benefit with access to GLP-1s"
    if "exclusive wellness benefit" in t:
        return "Introducing Digbi Health: An Exclusive Wellness Benefit with access to GLP-1s"
    # Fine Tuning
    if "fine" in t and ("tun" in t or "wl" in t or "4.99" in t or "weight loss" in t):
        return "Fine Tuning (2-4.99% WL)"
    # IBS
    if "ibs" in t or "irritable" in t:
        return "Thriving with IBS"

    return "Other"


def fmt_month(ym: str) -> str:
    try:
        return datetime.strptime(ym, "%Y-%m").strftime("%b %Y")
    except Exception:
        return ym


def parse_month(label: str) -> str:
    try:
        return datetime.strptime(label, "%b %Y").strftime("%Y-%m")
    except Exception:
        return label


# ── OAuth helpers ─────────────────────────────────────────────────────────────
def get_auth_url() -> str:
    params = {"response_type": "code", "client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI}
    return "https://zoom.us/oauth/authorize?" + urllib.parse.urlencode(params)


def exchange_code(code: str) -> dict:
    r = requests.post(
        "https://zoom.us/oauth/token",
        params={"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI},
        auth=(CLIENT_ID, CLIENT_SECRET),
    )
    r.raise_for_status()
    return r.json()


def refresh_token_fn(refresh_token: str) -> dict:
    r = requests.post(
        "https://zoom.us/oauth/token",
        params={"grant_type": "refresh_token", "refresh_token": refresh_token},
        auth=(CLIENT_ID, CLIENT_SECRET),
    )
    r.raise_for_status()
    return r.json()


def get_headers() -> dict:
    token_data = st.session_state.get("token_data", {})
    expires_at = st.session_state.get("token_expires_at", 0)
    if datetime.utcnow().timestamp() >= expires_at - 60:
        try:
            new_data = refresh_token_fn(token_data["refresh_token"])
            st.session_state["token_data"] = new_data
            st.session_state["token_expires_at"] = (
                datetime.utcnow().timestamp() + new_data.get("expires_in", 3600)
            )
            token_data = new_data
        except Exception:
            st.error("Session expired. Please reconnect your Zoom account.")
            st.stop()
    return {"Authorization": f"Bearer {token_data['access_token']}"}


# ── Data fetching (cached) ────────────────────────────────────────────────────
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_all_webinars(user_id: str, from_date: str, to_date: str) -> list:
    webinars = []

    # Past webinars
    next_page = None
    while True:
        r = requests.get(
            f"{ZOOM_API_BASE}/users/{user_id}/webinars",
            headers=get_headers(),
            params={
                "type": "past", "from": from_date, "to": to_date,
                "page_size": 300, "next_page_token": next_page,
            },
        )
        if r.status_code != 200:
            break
        data = r.json()
        webinars.extend(data.get("webinars", []))
        next_page = data.get("next_page_token")
        if not next_page:
            break

    # Upcoming webinars
    next_page = None
    while True:
        r = requests.get(
            f"{ZOOM_API_BASE}/users/{user_id}/webinars",
            headers=get_headers(),
            params={"type": "upcoming", "page_size": 300, "next_page_token": next_page},
        )
        if r.status_code != 200:
            break
        data = r.json()
        webinars.extend(data.get("webinars", []))
        next_page = data.get("next_page_token")
        if not next_page:
            break

    # Deduplicate
    seen = set()
    unique = []
    for w in webinars:
        identifier = f"{w['id']}_{w['start_time']}"
        if identifier not in seen:
            seen.add(identifier)
            unique.append(w)
    return unique


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_participants(webinar_uuid: str) -> list:
    participants = []
    
    # Zoom requires double URL-encoding for UUIDs if they contain '/' or '//'
    safe_uuid = webinar_uuid
    if isinstance(safe_uuid, str) and (safe_uuid.startswith('/') or '//' in safe_uuid):
        safe_uuid = urllib.parse.quote(urllib.parse.quote(safe_uuid, safe=''), safe='')
        
    next_page = None
    while True:
        r = requests.get(
            f"{ZOOM_API_BASE}/past_webinars/{safe_uuid}/participants",
            headers=get_headers(),
            params={"page_size": 300, "next_page_token": next_page},
        )
        if r.status_code != 200:
            break
        data = r.json()
        participants.extend(data.get("participants", []))
        next_page = data.get("next_page_token")
        if not next_page:
            break
    return participants


def get_user_id() -> str:
    r = requests.get(f"{ZOOM_API_BASE}/users/me", headers=get_headers())
    r.raise_for_status()
    return r.json()["id"]


# ── Main dashboard ────────────────────────────────────────────────────────────
def render_dashboard():
    # ── Sidebar: date range ───────────────────────────────────────────────────
    st.sidebar.header("Date Range")
    today        = date.today()
    default_from = date(today.year, 1, 1)
    from_date    = st.sidebar.date_input("From", value=default_from)
    to_date      = st.sidebar.date_input("To",   value=today + timedelta(days=60))

    if from_date > to_date:
        st.sidebar.error("'From' must be before 'To'.")
        return

    # ── Load data ─────────────────────────────────────────────────────────────
    with st.spinner("Loading webinars..."):
        user_id  = get_user_id()
        webinars = fetch_all_webinars(user_id, str(from_date), str(to_date))

    if not webinars:
        st.warning("No webinars found in this date range.")
        return

    all_participants = []
    progress = st.progress(0, text="Loading participant data...")
    now_utc  = datetime.now(timezone.utc)

    for i, wb in enumerate(webinars):
        raw_time = wb.get("start_time", "").replace("Z", "+00:00")
        try:
            utc_time      = datetime.fromisoformat(raw_time)
            pst_time      = utc_time.astimezone(ZoneInfo("America/Los_Angeles"))
            session_date  = pst_time.strftime("%Y-%m-%d")
            session_month = pst_time.strftime("%Y-%m")
            is_past       = utc_time < now_utc
        except ValueError:
            session_date  = raw_time[:10]
            session_month = raw_time[:7]
            is_past       = False

        series = map_to_series(wb.get("topic", ""))
        wb["session_date"]  = session_date
        wb["session_month"] = session_month
        wb["series"]        = series

        if is_past:
            # Zoom API needs the unique occurrence UUID to fetch participants for recurring meetings
            target_id = str(wb.get("uuid", wb.get("id")))
            pcts = fetch_participants(target_id)
            time.sleep(0.1)
            for p in pcts:
                p["webinar_id"]    = wb["id"]
                p["webinar_topic"] = wb.get("topic", "Unknown")
                p["series"]        = series
                p["session_date"]  = session_date
                p["session_month"] = session_month
                p["join_url"]      = wb.get("join_url", "")
            all_participants.extend(pcts)

        progress.progress(
            (i + 1) / len(webinars),
            text=f"Processing session {i + 1}/{len(webinars)}",
        )
    progress.empty()

    df_wb   = pd.DataFrame(webinars)
    df_part = pd.DataFrame(all_participants) if all_participants else pd.DataFrame()

    if not df_wb.empty:
        df_wb["month_label"] = df_wb["session_month"].apply(fmt_month)
        if "join_url" not in df_wb.columns:
            df_wb["join_url"] = ""
        df_wb["webinar_link"] = df_wb["join_url"]

    # ── Sidebar: filters ──────────────────────────────────────────────────────
    st.sidebar.header("Filters")

    all_series = sorted(df_wb["series"].unique().tolist()) if not df_wb.empty else []
    sel_series = st.sidebar.multiselect("Coaching Series", options=all_series, default=[])

    raw_months       = sorted(df_wb["session_month"].unique().tolist()) if not df_wb.empty else []
    month_labels     = [fmt_month(m) for m in raw_months]
    sel_month_labels = st.sidebar.multiselect("Month", options=month_labels, default=[])
    sel_months       = [parse_month(lbl) for lbl in sel_month_labels]

    # ── Apply filters ─────────────────────────────────────────────────────────
    mask_wb = pd.Series([True] * len(df_wb), index=df_wb.index)
    mask_wb &= df_wb["session_date"] >= str(from_date)
    mask_wb &= df_wb["session_date"] <= str(to_date)
    if sel_series: mask_wb &= df_wb["series"].isin(sel_series)
    if sel_months: mask_wb &= df_wb["session_month"].isin(sel_months)
    df_wb_f = df_wb[mask_wb].copy()

    if not df_part.empty:
        mask_p = pd.Series([True] * len(df_part), index=df_part.index)
        mask_p &= df_part["session_date"] >= str(from_date)
        mask_p &= df_part["session_date"] <= str(to_date)
        if sel_series: mask_p &= df_part["series"].isin(sel_series)
        if sel_months: mask_p &= df_part["session_month"].isin(sel_months)
        df_part_f = df_part[mask_p].copy()
    else:
        df_part_f = pd.DataFrame()

    # ── Top-level KPI strip ───────────────────────────────────────────────────
    st.title("Digbi Health - Group Coaching Dashboard")

    # KPIs only count official coaching series (not "Other")
    df_wb_core   = df_wb_f[df_wb_f["series"] != "Other"]
    df_part_core = (
        df_part_f[df_part_f["series"] != "Other"]
        if not df_part_f.empty
        else pd.DataFrame()
    )

    k1, k2, k3, k4 = st.columns(4)
    total_sessions  = len(df_wb_core)
    total_attendees = len(df_part_core)
    unique_members  = (
        df_part_core["user_email"].nunique()
        if not df_part_core.empty and "user_email" in df_part_core.columns
        else 0
    )
    avg_sessions_per_member = round(total_attendees / unique_members, 2) if unique_members else 0

    k1.metric("Total Sessions",          total_sessions)
    k2.metric("Total Attendees",         total_attendees)
    k3.metric("Unique Members",          unique_members)
    k4.metric("Avg Sessions / Attendee", avg_sessions_per_member)
    st.markdown("---")

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab_overview, tab_series, tab_month, tab_participants, tab_raw = st.tabs([
        "Overview", "By Series", "By Month", "Participants", "Raw Data",
    ])

    # ▐▐▐ TAB 1 — OVERVIEW ▌▌▌
    with tab_overview:
        st.subheader("Stats for 7 Recurring Webinars")

        base_df = pd.DataFrame({"series": COACHING_SERIES})

        if df_wb_f.empty:
            stats_df = base_df.copy()
            stats_df["Sessions"]                  = 0
            stats_df["Total_Attendees"]           = 0
            stats_df["Unique_Members"]            = 0
            stats_df["Avg_Sessions_Per_Attendee"] = 0.0
        else:
            wb_stats = df_wb_f.groupby("series").size().reset_index(name="Sessions")

            if not df_part_f.empty:
                part_stats = df_part_f.groupby("series").agg(
                    Total_Attendees=("user_email", "count"),
                    Unique_Members=("user_email", "nunique"),
                ).reset_index()
            else:
                part_stats = pd.DataFrame(columns=["series", "Total_Attendees", "Unique_Members"])

            stats_df = pd.merge(base_df, wb_stats,   on="series", how="left").fillna(0)
            stats_df = pd.merge(stats_df, part_stats, on="series", how="left").fillna(0)
            stats_df["Avg_Sessions_Per_Attendee"] = 0.0
            mask = stats_df["Unique_Members"] > 0
            if mask.any():
                stats_df.loc[mask, "Avg_Sessions_Per_Attendee"] = (
                    stats_df.loc[mask, "Total_Attendees"] / stats_df.loc[mask, "Unique_Members"]
                ).round(2)

        stats_df["Sessions"]        = stats_df["Sessions"].astype(int)
        stats_df["Total_Attendees"] = stats_df["Total_Attendees"].astype(int)
        stats_df["Unique_Members"]  = stats_df["Unique_Members"].astype(int)

        stats_df = stats_df.rename(columns={
            "series":                    "Coaching Series",
            "Total_Attendees":           "Total Attendees",
            "Unique_Members":            "Unique Members",
            "Avg_Sessions_Per_Attendee": "Avg Sessions / Attendee",
        })
        st.dataframe(
            stats_df.sort_values("Total Attendees", ascending=False),
            use_container_width=True,
            hide_index=True,
        )

    # ▐▐▐ TAB 2 — BY SERIES ▌▌▌
    with tab_series:
        if df_wb_f.empty:
            st.info("No sessions match.")
        else:
            series_list   = sorted(df_wb_f["series"].unique().tolist())
            chosen_series = st.selectbox("Select a series to inspect:", series_list)
            df_s   = df_wb_f[df_wb_f["series"] == chosen_series].copy()
            df_p_s = (
                df_part_f[df_part_f["series"] == chosen_series].copy()
                if not df_part_f.empty
                else pd.DataFrame()
            )

            st.subheader("Session & Registration Log")
            if not df_s.empty:
                if not df_p_s.empty:
                    att_counts = df_p_s.groupby("webinar_id").size().reset_index(name="attendees")
                    df_log = df_s.merge(att_counts, left_on="id", right_on="webinar_id", how="left")
                    df_log["attendees"] = df_log["attendees"].fillna(0).astype(int)
                else:
                    df_log = df_s.copy()
                    df_log["attendees"] = 0

                df_log = df_log.sort_values("session_date", ascending=False)
                for _, row in df_log.iterrows():
                    link    = row.get("webinar_link", "")
                    d_str   = str(row.get("session_date", ""))
                    topic   = row.get("topic", "")
                    att     = row.get("attendees", 0)
                    month_l = (
                        fmt_month(str(row.get("session_month", ""))[:7])
                        if row.get("session_month") else ""
                    )
                    is_upcoming = " **[UPCOMING]**" if str(date.today()) <= d_str else ""
                    if link:
                        st.markdown(
                            f"{is_upcoming} **{d_str}** ({month_l}) &nbsp; {topic}"
                            f" &nbsp;&nbsp; Attendees: **{att}** &nbsp;&nbsp; [Webinar Link]({link})"
                        )
                    else:
                        st.markdown(
                            f"{is_upcoming} **{d_str}** ({month_l}) &nbsp; {topic}"
                            f" &nbsp;&nbsp; Attendees: **{att}**"
                        )

    # ▐▐▐ TAB 3 — BY MONTH ▌▌▌
    with tab_month:
        if df_part_f.empty:
            st.info("No participant data available.")
        else:
            monthly_summary = (
                df_part_f.groupby("session_month")
                .agg(
                    sessions=("webinar_id", "nunique"),
                    attendances=("user_email", "count"),
                )
                .reset_index()
                .sort_values("session_month", ascending=False)
            )
            monthly_summary["Month"] = monthly_summary["session_month"].apply(fmt_month)
            st.dataframe(
                monthly_summary[["Month", "sessions", "attendances"]],
                use_container_width=True,
                hide_index=True,
            )

    # ▐▐▐ TAB 4 — PARTICIPANTS ▌▌▌
    with tab_participants:
        if df_part_f.empty:
            st.info("No participant data available.")
        else:
            search_q  = st.text_input("Search by name or email")
            df_search = df_part_f.copy()
            if search_q:
                q    = search_q.lower()
                mask = (
                    df_search["name"].str.lower().str.contains(q, na=False)
                    | df_search["user_email"].str.lower().str.contains(q, na=False)
                )
                df_search = df_search[mask]
            st.dataframe(
                df_search[["name", "user_email", "series", "session_date"]].sort_values(
                    "session_date", ascending=False
                ),
                use_container_width=True,
                hide_index=True,
            )

    # ▐▐▐ TAB 5 — RAW DATA ▌▌▌
    with tab_raw:
        st.subheader("All Fetched Webinars (including Other)")
        if not df_wb.empty:
            # Show ALL webinars (unfiltered) so you can see exact topic strings and series mapping
            display_cols = ["session_date", "month_label", "series", "topic", "id"]
            st.dataframe(
                df_wb[display_cols].sort_values("session_date", ascending=False),
                use_container_width=True,
                hide_index=True,
            )
            # Topic → Series mapping summary (debug)
            st.markdown("---")
            st.subheader("Topic → Series Mapping Summary")
            mapping_summary = (
                df_wb.groupby(["topic", "series"])
                .size()
                .reset_index(name="count")
                .sort_values("series")
            )
            st.dataframe(mapping_summary, use_container_width=True, hide_index=True)


# ── Password gate ────────────────────────────────────────────────────────────
def check_password() -> bool:
    """Return True once the correct app password has been entered.

    Password is read from st.secrets["APP_PASSWORD"].
    If the secret is not set, the gate is skipped (dev mode).
    """
    app_password = st.secrets.get("APP_PASSWORD", "")
    if not app_password:
        return True  # No password configured → open access (dev/local)

    if st.session_state.get("_authenticated"):
        return True

    st.title("Digbi Health - Group Coaching Dashboard")
    st.markdown("This dashboard is for **internal use only**. Please enter the access password.")

    col, _ = st.columns([1, 2])
    with col:
        pwd = st.text_input("Password", type="password", key="_pwd_input")
        if st.button("Enter", key="_pwd_submit"):
            if pwd == app_password:
                st.session_state["_authenticated"] = True
                st.rerun()
            else:
                st.error("Incorrect password.")
    st.stop()
    return False  # unreachable but satisfies type checkers


# ── Auth flow & app entry point ───────────────────────────────────────────────
def main():
    if not check_password():
        return

    query_params = st.query_params
    if "code" in query_params and "token_data" not in st.session_state:
        try:
            token_data = exchange_code(query_params["code"])
            st.session_state["token_data"]       = token_data
            st.session_state["token_expires_at"] = (
                datetime.utcnow().timestamp() + token_data.get("expires_in", 3600)
            )
            st.query_params.clear()
            st.rerun()
        except Exception as e:
            st.error(f"OAuth error: {e}")
            return

    if "token_data" not in st.session_state:
        st.title("Digbi Health - Group Coaching Dashboard")
        st.markdown("Connect your Zoom account to view Group Coaching analytics.")
        auth_url    = get_auth_url()
        button_html = f"""
        <a href="{auth_url}" target="_self" style="
            background-color: #FF4B4B;
            color: white;
            padding: 10px 20px;
            text-align: center;
            text-decoration: none;
            display: inline-block;
            border-radius: 5px;
            font-weight: 500;
            font-family: sans-serif;">
            Connect Zoom Account
        </a>
        """
        st.markdown(button_html, unsafe_allow_html=True)
        return

    with st.sidebar:
        st.markdown("---")
        if st.button("Disconnect Zoom", key="sidebar_disconnect_zoom"):
            for key in ["token_data", "token_expires_at"]:
                st.session_state.pop(key, None)
            st.rerun()

    render_dashboard()


if __name__ == "__main__":
    main()