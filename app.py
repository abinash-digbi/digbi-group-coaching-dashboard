"""
Digbi Health â Group Coaching Dashboard
Zoom Webinars API Â· Streamlit Cloud
"""

import os
import urllib.parse
import requests
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, date

# ââ Page config ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
st.set_page_config(
    page_title="Digbi Group Coaching",
    page_icon="ð§¬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ââ Zoom credentials from Streamlit secrets ââââââââââââââââââââââââââââââââââ
CLIENT_ID     = st.secrets["ZOOM_CLIENT_ID"]
CLIENT_SECRET = st.secrets["ZOOM_CLIENT_SECRET"]
REDIRECT_URI  = st.secrets["ZOOM_REDIRECT_URI"]
ZOOM_API_BASE = "https://api.zoom.us/v2"

# ââ The 7 recurring Group Coaching series ââââââââââââââââââââââââââââââââââââ
COACHING_SERIES = [
    "Orientation + Eat Smart [Employer]",
    "Orientation + Eat Smart [Solera]",
    "How to Read Gene & Gut Kit",
    "How to Read Gut Kit",
    "Living Well with GLP-1",
    "Fine Tuning (2-4.99% WL)",
    "Thriving with IBS",
]

SERIES_COLORS = {
    "Orientation + Eat Smart [Employer]": "#1f77b4",
    "Orientation + Eat Smart [Solera]":   "#ff7f0e",
    "How to Read Gene & Gut Kit":         "#2ca02c",
    "How to Read Gut Kit":                "#d62728",
    "Living Well with GLP-1":             "#9467bd",
    "Fine Tuning (2-4.99% WL)":           "#8c564b",
    "Thriving with IBS":                  "#e377c2",
    "Other":                              "#7f7f7f",
}

# Recurring Zoom webinar links (static â same IDs reused every session)
WEBINAR_LINKS = {
    "Orientation + Eat Smart [Employer]": "https://us02web.zoom.us/webinar/87592551115",
    "Orientation + Eat Smart [Solera]":   "https://us02web.zoom.us/webinar/84993510536",
    "Living Well with GLP-1":             "https://us02web.zoom.us/webinar/86297068882",
    "Fine Tuning (2-4.99% WL)":           "https://us02web.zoom.us/webinar/82971897843",
    "Thriving with IBS":                  "https://us02web.zoom.us/webinar/83049291192",
    "How to Read Gene & Gut Kit":         "https://us02web.zoom.us/webinar/88933558702",
    "How to Read Gut Kit":                "https://us02web.zoom.us/webinar/81840645742",
}

# Recurring schedule details
SERIES_SCHEDULE = {
    "Orientation + Eat Smart [Employer]": {"frequency": "Every 2 weeks", "day": "Friday",   "time": "11:00â11:45 AM PST", "audience": "Employer"},
    "Orientation + Eat Smart [Solera]":   {"frequency": "Every 2 weeks", "day": "Friday",   "time": "12:00â12:45 PM PST", "audience": "Solera"},
    "How to Read Gene & Gut Kit":         {"frequency": "Every 3 weeks", "day": "Friday",   "time": "11:00â11:45 AM PST", "audience": "Employer"},
    "How to Read Gut Kit":                {"frequency": "Every 3 weeks", "day": "Friday",   "time": "12:00â12:45 PM PST", "audience": "Solera"},
    "Living Well with GLP-1":             {"frequency": "Every 3 weeks", "day": "Thursday", "time": "11:00â11:45 AM PST", "audience": "All Members"},
    "Fine Tuning (2-4.99% WL)":           {"frequency": "Every 2 weeks", "day": "Thursday", "time": "12:00â12:45 PM PST", "audience": "All Members"},
    "Thriving with IBS":                  {"frequency": "Every 2 weeks", "day": "Thursday", "time": "11:00â11:45 AM PST", "audience": "All Members"},
}


def map_to_series(topic: str) -> str:
    """Map a raw webinar topic string to one of the 7 coaching series."""
    if not isinstance(topic, str):
        return "Other"
    t = topic.lower()
    # Solera variants â must be checked before generic Employer/Orientation checks
    if "solera" in t and ("orientation" in t or "eat smart" in t or "gut only" in t):
        return "Orientation + Eat Smart [Solera]"
    if "gut only" in t and ("orientation" in t or "eat smart" in t):
        return "Orientation + Eat Smart [Solera]"
    # Employer variants
    if ("orientation" in t or "eat smart" in t) and ("employer" in t or "full product" in t):
        return "Orientation + Eat Smart [Employer]"
    # Catch broad orientation/eat smart (Employer is default audience)
    if "orientation" in t and "eat smart" in t:
        return "Orientation + Eat Smart [Employer]"
    # Gene & Gut Kit (Employer) â gene check must precede plain gut kit check
    if "gene" in t and "gut" in t:
        return "How to Read Gene & Gut Kit"
    # Gut Kit (Solera)
    if "gut kit" in t or ("read" in t and "gut" in t):
        return "How to Read Gut Kit"
    # GLP-1
    if "glp" in t or "glp-1" in t or "semaglutide" in t or "ozempic" in t:
        return "Living Well with GLP-1"
    # Fine Tuning
    if "fine" in t and ("tun" in t or "wl" in t or "4.99" in t or "weight loss" in t):
        return "Fine Tuning (2-4.99% WL)"
    # IBS
    if "ibs" in t or "irritable" in t:
        return "Thriving with IBS"
    return "Other"


def extract_company(email: str) -> str:
    """Infer company name from email domain."""
    personal = {
        "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com",
        "aol.com", "protonmail.com", "live.com", "me.com", "msn.com",
        "googlemail.com", "ymail.com", "mail.com",
    }
    if not isinstance(email, str) or "@" not in email:
        return "Unknown"
    domain = email.split("@")[-1].lower().strip()
    if domain in personal:
        return "Personal Email"
    parts = domain.split(".")
    return parts[-2].title() if len(parts) >= 2 else domain.title()


def fmt_month(ym: str) -> str:
    """Convert 'YYYY-MM' to 'Jan 2026'."""
    try:
        return datetime.strptime(ym, "%Y-%m").strftime("%b %Y")
    except Exception:
        return ym


def parse_month(label: str) -> str:
    """Convert 'Jan 2026' to 'YYYY-MM' for sorting."""
    try:
        return datetime.strptime(label, "%b %Y").strftime("%Y-%m")
    except Exception:
        return label


# ââ OAuth helpers âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def get_auth_url() -> str:
    params = {
        "response_type": "code",
        "client_id":     CLIENT_ID,
        "redirect_uri":  REDIRECT_URI,
    }
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


# ââ Data fetching (cached) ââââââââââââââââââââââââââââââââââââââââââââââââââââ

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_webinars(user_id: str, from_date: str, to_date: str) -> list:
    """Fetch past webinars for a user within date range."""
    webinars = []
    next_page = None
    while True:
        params = {"type": "past", "from": from_date, "to": to_date, "page_size": 300}
        if next_page:
            params["next_page_token"] = next_page
        r = requests.get(
            f"{ZOOM_API_BASE}/users/{user_id}/webinars",
            headers=get_headers(),
            params=params,
        )
        if r.status_code != 200:
            break
        data = r.json()
        webinars.extend(data.get("webinars", []))
        next_page = data.get("next_page_token")
        if not next_page:
            break
    return webinars


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_participants(webinar_id: str) -> list:
    """Fetch attendees for a past webinar."""
    participants = []
    next_page = None
    while True:
        params = {"page_size": 300}
        if next_page:
            params["next_page_token"] = next_page
        r = requests.get(
            f"{ZOOM_API_BASE}/past_webinars/{webinar_id}/participants",
            headers=get_headers(),
            params=params,
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


# ââ Main dashboard ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def render_dashboard():
    # ââ Sidebar: date range âââââââââââââââââââââââââââââââââââââââââââââââââââ
    st.sidebar.header("Date Range")
    today        = date.today()
    default_from = today - timedelta(days=365)
    from_date    = st.sidebar.date_input("From", value=default_from)
    to_date      = st.sidebar.date_input("To",   value=today)

    if from_date > to_date:
        st.sidebar.error("'From' must be before 'To'.")
        return

    # ââ Load data âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    with st.spinner("Loading webinars..."):
        user_id  = get_user_id()
        webinars = fetch_webinars(user_id, str(from_date), str(to_date))

    if not webinars:
        st.warning("No webinars found in this date range.")
        return

    # Build participant DataFrame
    all_participants = []
    progress = st.progress(0, text="Loading participant data...")
    for i, wb in enumerate(webinars):
        pcts   = fetch_participants(wb["id"])
        series = map_to_series(wb.get("topic", ""))
        for p in pcts:
            p["webinar_id"]    = wb["id"]
            p["webinar_topic"] = wb.get("topic", "Unknown")
            p["series"]        = series
            p["session_date"]  = wb.get("start_time", "")[:10]
            p["session_month"] = wb.get("start_time", "")[:7]   # YYYY-MM
            p["join_url"]      = wb.get("join_url", "")
            p["company"]       = extract_company(p.get("user_email", ""))
        all_participants.extend(pcts)
        progress.progress(
            (i + 1) / len(webinars),
            text=f"Loading participant data... {i+1}/{len(webinars)}"
        )
    progress.empty()

    df_wb   = pd.DataFrame(webinars)
    df_part = pd.DataFrame(all_participants) if all_participants else pd.DataFrame()

    # Enrich webinar DataFrame
    if not df_wb.empty:
        df_wb["series"]        = df_wb["topic"].apply(map_to_series)
        df_wb["session_date"]  = pd.to_datetime(df_wb["start_time"], errors="coerce").dt.date
        df_wb["session_month"] = (
            pd.to_datetime(df_wb["start_time"], errors="coerce")
            .dt.to_period("M").astype(str)
        )
        df_wb["month_label"]   = df_wb["session_month"].apply(fmt_month)
        if "join_url" not in df_wb.columns:
            df_wb["join_url"] = ""
        # Fall back to static recurring webinar link for each series
        df_wb["webinar_link"] = df_wb.apply(
            lambda r: r["join_url"] or WEBINAR_LINKS.get(r["series"], ""), axis=1
        )

    # ââ Sidebar: filters ââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    st.sidebar.header("Filters")

    all_series = sorted(df_wb["series"].unique().tolist()) if not df_wb.empty else []
    sel_series = st.sidebar.multiselect(
        "Coaching Series",
        options=all_series,
        default=[],
        placeholder="All series",
    )

    # Month options as "Jan 2026" etc.
    raw_months   = sorted(df_wb["session_month"].unique().tolist()) if not df_wb.empty else []
    month_labels = [fmt_month(m) for m in raw_months]
    sel_month_labels = st.sidebar.multiselect(
        "Month",
        options=month_labels,
        default=[],
        placeholder="All months",
    )
    sel_months = [parse_month(lbl) for lbl in sel_month_labels]

    all_companies = []
    if not df_part.empty and "company" in df_part.columns:
        all_companies = sorted(df_part["company"].dropna().unique().tolist())
    sel_companies = st.sidebar.multiselect(
        "Company",
        options=all_companies,
        default=[],
        placeholder="All companies",
    )

    # Apply filters
    mask_wb = pd.Series([True] * len(df_wb), index=df_wb.index)
    if sel_series:
        mask_wb &= df_wb["series"].isin(sel_series)
    if sel_months:
        mask_wb &= df_wb["session_month"].isin(sel_months)
    df_wb_f = df_wb[mask_wb].copy()

    if not df_part.empty:
        mask_p = pd.Series([True] * len(df_part), index=df_part.index)
        if sel_series:
            mask_p &= df_part["series"].isin(sel_series)
        if sel_months:
            mask_p &= df_part["session_month"].isin(sel_months)
        if sel_companies:
            mask_p &= df_part["company"].isin(sel_companies)
        df_part_f = df_part[mask_p].copy()
    else:
        df_part_f = pd.DataFrame()

    # ââ Top-level KPI strip âââââââââââââââââââââââââââââââââââââââââââââââââââ
    st.title("Digbi Health - Group Coaching Dashboard")
    if sel_series or sel_months or sel_companies:
        parts = []
        if sel_series:       parts.append(f"Series: {', '.join(sel_series)}")
        if sel_month_labels: parts.append(f"Months: {', '.join(sel_month_labels)}")
        if sel_companies:    parts.append(f"Companies: {', '.join(sel_companies)}")
        st.caption("Filtered by: " + " | ".join(parts))

    k1, k2, k3, k4, k5 = st.columns(5)
    total_sessions   = len(df_wb_f)
    total_attendees  = len(df_part_f)
    unique_members   = df_part_f["user_email"].nunique() if not df_part_f.empty and "user_email" in df_part_f.columns else 0
    unique_companies = df_part_f["company"].nunique()    if not df_part_f.empty and "company"    in df_part_f.columns else 0
    avg_per_session  = round(total_attendees / total_sessions, 1) if total_sessions else 0

    k1.metric("Sessions",        total_sessions)
    k2.metric("Total Attendees", total_attendees)
    k3.metric("Unique Members",  unique_members)
    k4.metric("Companies",       unique_companies)
    k5.metric("Avg / Session",   avg_per_session)

    st.markdown("---")

    # ââ Tabs ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    tab_overview, tab_series, tab_company, tab_month, tab_participants, tab_raw = st.tabs([
        "Overview",
        "By Series",
        "By Company",
        "By Month",
        "Participants",
        "Raw Data",
    ])

    # ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    # TAB 1 â OVERVIEW
    # ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    with tab_overview:
        if df_wb_f.empty:
            st.info("No sessions match the current filters.")
        else:
            col_a, col_b = st.columns(2)

            with col_a:
                sess_by_series = (
                    df_wb_f.groupby("series")
                    .size()
                    .reset_index(name="sessions")
                    .sort_values("sessions", ascending=True)
                )
                fig = px.bar(
                    sess_by_series,
                    x="sessions", y="series", orientation="h",
                    title="Sessions per Coaching Series",
                    color="series",
                    color_discrete_map=SERIES_COLORS,
                    labels={"series": "", "sessions": "Sessions"},
                )
                fig.update_layout(showlegend=False, height=350)
                st.plotly_chart(fig, use_container_width=True)

            with col_b:
                if not df_part_f.empty:
                    att_by_series = (
                        df_part_f.groupby("series")
                        .size()
                        .reset_index(name="attendees")
                        .sort_values("attendees", ascending=True)
                    )
                    fig2 = px.bar(
                        att_by_series,
                        x="attendees", y="series", orientation="h",
                        title="Total Attendees per Coaching Series",
                        color="series",
                        color_discrete_map=SERIES_COLORS,
                        labels={"series": "", "attendees": "Attendees"},
                    )
                    fig2.update_layout(showlegend=False, height=350)
                    st.plotly_chart(fig2, use_container_width=True)

            if not df_part_f.empty and "session_month" in df_part_f.columns:
                st.subheader("Attendance Trend by Month")
                trend = (
                    df_part_f.groupby(["session_month", "series"])
                    .size()
                    .reset_index(name="attendees")
                )
                trend["month_label"] = trend["session_month"].apply(fmt_month)
                trend_sorted = trend.sort_values("session_month")
                fig3 = px.line(
                    trend_sorted,
                    x="month_label", y="attendees", color="series",
                    title="Monthly Attendance by Coaching Series",
                    color_discrete_map=SERIES_COLORS,
                    markers=True,
                    labels={"month_label": "Month", "attendees": "Attendees", "series": "Series"},
                )
                fig3.update_layout(height=420, xaxis_tickangle=-30)
                st.plotly_chart(fig3, use_container_width=True)

            # Series Reference Table
            st.markdown("---")
            st.subheader("ð Recurring Series Reference")
            ref_rows = []
            for s in COACHING_SERIES:
                sc = SERIES_SCHEDULE.get(s, {})
                ref_rows.append({
                    "Series":     s,
                    "Audience":   sc.get("audience", ""),
                    "Frequency":  sc.get("frequency", ""),
                    "Day":        sc.get("day", ""),
                    "Time (PST)": sc.get("time", ""),
                    "Webinar Link": WEBINAR_LINKS.get(s, ""),
                })
            df_ref = pd.DataFrame(ref_rows)

            def make_link(url):
                return f'<a href="{url}" target="_blank">Join Webinar</a>' if url else ""

            df_ref["Webinar Link"] = df_ref["Webinar Link"].apply(make_link)
            st.markdown(
                df_ref.to_html(escape=False, index=False),
                unsafe_allow_html=True,
            )

    # ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    # TAB 2 â BY SERIES
    # ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    with tab_series:
        if df_wb_f.empty:
            st.info("No sessions match the current filters.")
        else:
            series_list   = sorted(df_wb_f["series"].unique().tolist())
            chosen_series = st.selectbox("Select a series to inspect:", series_list)

            df_s   = df_wb_f[df_wb_f["series"] == chosen_series].copy()
            df_p_s = df_part_f[df_part_f["series"] == chosen_series].copy() if not df_part_f.empty else pd.DataFrame()

            # Series info card
            sched = SERIES_SCHEDULE.get(chosen_series, {})
            webinar_url = WEBINAR_LINKS.get(chosen_series, "")
            if sched:
                info_cols = st.columns([1, 1, 1, 1, 2])
                info_cols[0].markdown(f"ðï¸ **{sched.get('frequency', '')}**")
                info_cols[1].markdown(f"ð **{sched.get('day', '')}**")
                info_cols[2].markdown(f"ð **{sched.get('time', '')}**")
                info_cols[3].markdown(f"ð¥ **{sched.get('audience', '')}**")
                if webinar_url:
                    info_cols[4].markdown(f"[ð Join Recurring Webinar]({webinar_url})")
                st.markdown("---")

            s1, s2, s3, s4 = st.columns(4)
            s1.metric("Sessions",       len(df_s))
            s2.metric("Total Attendees", len(df_p_s))
            s3.metric("Unique Members",  df_p_s["user_email"].nunique() if not df_p_s.empty and "user_email" in df_p_s.columns else 0)
            s4.metric("Avg / Session",   round(len(df_p_s) / len(df_s), 1) if len(df_s) else 0)

            col1, col2 = st.columns(2)

            with col1:
                if not df_p_s.empty and "session_date" in df_p_s.columns:
                    att_date = (
                        df_p_s.groupby("session_date")
                        .size()
                        .reset_index(name="attendees")
                        .sort_values("session_date")
                    )
                    fig = px.bar(
                        att_date, x="session_date", y="attendees",
                        title=f"Attendance Per Session",
                        labels={"session_date": "Date", "attendees": "Attendees"},
                        color_discrete_sequence=[SERIES_COLORS.get(chosen_series, "#1f77b4")],
                    )
                    fig.update_layout(height=300, xaxis_tickangle=-30)
                    st.plotly_chart(fig, use_container_width=True)

            with col2:
                if not df_p_s.empty and "company" in df_p_s.columns:
                    top_co = (
                        df_p_s[df_p_s["company"] != "Personal Email"]
                        .groupby("company")
                        .size()
                        .reset_index(name="attendees")
                        .sort_values("attendees", ascending=False)
                        .head(10)
                    )
                    fig2 = px.bar(
                        top_co.sort_values("attendees"),
                        x="attendees", y="company", orientation="h",
                        title="Top Companies",
                        labels={"company": "", "attendees": "Attendees"},
                        color_discrete_sequence=[SERIES_COLORS.get(chosen_series, "#1f77b4")],
                    )
                    fig2.update_layout(height=300)
                    st.plotly_chart(fig2, use_container_width=True)

            # Session log with webinar links
            st.subheader("Session Log")
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
                    link    = row.get("webinar_link", "") or WEBINAR_LINKS.get(row.get("series", ""), "")
                    d_str   = str(row.get("session_date", ""))
                    topic   = row.get("topic", "")
                    att     = row.get("attendees", 0)
                    month_l = fmt_month(str(row.get("session_month", ""))[:7]) if row.get("session_month") else ""
                    if link:
                        st.markdown(f"**{d_str}** ({month_l}) &nbsp; {topic} &nbsp;&nbsp; Attendees: **{att}** &nbsp;&nbsp; [Webinar Link]({link})")
                    else:
                        st.markdown(f"**{d_str}** ({month_l}) &nbsp; {topic} &nbsp;&nbsp; Attendees: **{att}**")

    # ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    # TAB 3 â BY COMPANY
    # ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    with tab_company:
        if df_part_f.empty:
            st.info("No participant data available.")
        else:
            company_summary = (
                df_part_f[df_part_f["company"] != "Personal Email"]
                .groupby("company")
                .agg(
                    total_attendances=("user_email", "count"),
                    unique_members=("user_email", "nunique"),
                    series_attended=("series", lambda x: len(x.unique())),
                )
                .reset_index()
                .sort_values("total_attendances", ascending=False)
            )

            st.subheader(f"Company Attendance Summary  â  .len(company_summary) companies")
            st.dataframe(
                company_summary.rename(columns={
                    "company":           "Company",
                    "total_attendances": "Total Attendances",
                    "unique_members":    "Unique Members",
                    "series_attended":   "Series Attended",
                }),
                use_container_width=True,
                hide_index=True,
            )

            top15 = company_summary.head(15).sort_values("total_attendances")
            fig = px.bar(
                top15,
                x="total_attendances", y="company", orientation="h",
                title="Top 15 Companies by Total Attendances",
                labels={"company": "", "total_attendances": "Attendances"},
                color="series_attended",
                color_continuous_scale="Blues",
            )
            fig.update_layout(height=450)
            st.plotly_chart(fig, use_container_width=True)

            st.markdown("---")
            st.subheader("Company Deep-Dive")
            all_cos    = ["(Select a company)"] + company_summary["company"].tolist()
            chosen_co  = st.selectbox("Select company:", all_cos)

            if chosen_co != "(Select a company)":
                df_co = df_part_f[df_part_f["company"] == chosen_co].copy()

                c1, c2, c3 = st.columns(3)
                c1.metric("Total Attendances", len(df_co))
                c2.metric("Unique Members",    df_co["user_email"].nunique() if "user_email" in df_co.columns else 0)
                c3.metric("Series Attended",   df_co["series"].nunique()     if "series"     in df_co.columns else 0)

                col_l, col_r = st.columns(2)
                with col_l:
                    series_bd = df_co.groupby("series").size().reset_index(name="attendances")
                    fig_co = px.pie(
                        series_bd, values="attendances", names="series",
                        title=f"{chosen_co} â Attendance by Series",
                        color="series", color_discrete_map=SERIES_COLORS,
                    )
                    fig_co.update_layout(height=300)
                    st.plotly_chart(fig_co, use_container_width=True)

                with col_r:
                    monthly_co = (
                        df_co.groupby("session_month")
                        .size().reset_index(name="attendances")
                        .sort_values("session_month")
                    )
                    monthly_co["month_label"] = monthly_co["session_month"].apply(fmt_month)
                    fig_m = px.bar(
                        monthly_co, x="month_label", y="attendances",
                        title=f"{chosen_co} â Monthly Attendance",
                        labels={"month_label": "Month", "attendances": "Attendances"},
                    )
                    fig_m.update_layout(height=300, xaxis_tickangle=-30)
                    st.plotly_chart(fig_m, use_container_width=True)

                st.subheader(f"Members from {chosen_co}")
                member_cols = [c for c in ["name", "user_email", "series", "session_date"] if c in df_co.columns]
                st.dataframe(
                    df_co[member_cols].rename(columns={
                        "name": "Name", "user_email": "Email",
                        "series": "Series", "session_date": "Date",
                    }).sort_values("Date", ascending=False),
                    use_container_width=True,
                    hide_index=True,
                )

    # ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    # TAB 4 â BY MONTH
    # ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    with tab_month:
        if df_part_f.empty:
            st.info("No participant data available.")
        else:
            monthly_summary = (
                df_part_f.groupby("session_month")
                .agg(
                    sessions=("webinar_id", "nunique"),
                    attendances=("user_email", "count"),
                    unique_members=("user_email", "nunique"),
                    companies=("company", "nunique"),
                )
                .reset_index()
                .sort_values("session_month", ascending=False)
            )
            monthly_summary["Month"] = monthly_summary["session_month"].apply(fmt_month)

            st.subheader("Monthly Summary")
            st.dataframe(
                monthly_summary[["Month", "sessions", "attendances", "unique_members", "companies"]].rename(columns={
                    "sessions":       "Sessions",
                    "attendances":    "Total Attendances",
                    "unique_members": "Unique Members",
                    "companies":      "Companies",
                }),
                use_container_width=True,
                hide_index=True,
            )

            # Series x Month heatmap
            st.subheader("Series x Month Heatmap")
            heat = (
                df_part_f.groupby(["series", "session_month"])
                .size().reset_index(name="attendances")
            )
            heat["month_label"] = heat["session_month"].apply(fmt_month)
            pivot = heat.pivot_table(
                index="series", columns="month_label",
                values="attendances", fill_value=0
            )
            sorted_cols = sorted(pivot.columns, key=lambda x: parse_month(x))
            pivot = pivot[sorted_cols]
            fig_h = px.imshow(
                pivot,
                text_auto=True,
                color_continuous_scale="Blues",
                title="Attendances per Series per Month",
                labels={"x": "Month", "y": "Series", "color": "Attendances"},
            )
            fig_h.update_layout(height=400)
            st.plotly_chart(fig_h, use_container_width=True)

            # Month drill-down
            st.markdown("---")
            st.subheader("Month Drill-Down")
            month_options = ["(Select a month)"] + [
                fmt_month(m)
                for m in sorted(df_part_f["session_month"].unique().tolist(), reverse=True)
            ]
            chosen_month_lbl = st.selectbox("Select month:", month_options)

            if chosen_month_lbl != "(Select a month)":
                chosen_month_raw = parse_month(chosen_month_lbl)
                df_m    = df_part_f[df_part_f["session_month"] == chosen_month_raw].copy()
                df_wb_m = df_wb_f[df_wb_f["session_month"]    == chosen_month_raw].copy()

                m1, m2, m3 = st.columns(3)
                m1.metric("Sessions",        len(df_wb_m))
                m2.metric("Attendances",     len(df_m))
                m3.metric("Unique Members",  df_m["user_email"].nunique() if "user_email" in df_m.columns else 0)

                st.subheader(f"Sessions in {chosen_month_lbl}")
                for _, row in df_wb_m.sort_values("session_date").iterrows():
                    wb_id  = row.get("id", "")
                    topic  = row.get("topic", "")
                    s_date = str(row.get("session_date", ""))
                    series = row.get("series", "")
                    link   = row.get("webinar_link", "") or WEBINAR_LINKS.get(series, "")
                    n_att  = len(df_m[df_m["webinar_id"] == wb_id]) if not df_m.empty else 0
                    if link:
                        st.markdown(f"**{s_date}** &nbsp; {series} &nbsp;&nbsp; Attendees: **{n_att}** &nbsp;&nbsp; [Webinar Link]({link})")
                    else:
                        st.markdown(f"**{s_date}** &nbsp; {series} &nbsp;&nbsp; Attendees: **{n_att}**")

    # ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    # TAB 5 â PARTICIPANTS
    # ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    with tab_participants:
        if df_part_f.empty:
            st.info("No participant data available.")
        else:
            search_q = st.text_input("Search by name or email", placeholder="e.g. Jane or jane@company.com")

            df_search = df_part_f.copy()
            if search_q:
                q    = search_q.lower()
                name_col  = df_search.get("name",       pd.Series([""] * len(df_search), index=df_search.index))
                email_col = df_search.get("user_email", pd.Series([""] * len(df_search), index=df_search.index))
                mask = (
                    name_col.str.lower().str.contains(q, na=False)
                    | email_col.str.lower().str.contains(q, na=False)
                )
                df_search = df_search[mask]

            if not search_q:
                st.subheader("Most Active Participants")
                if "user_email" in df_part_f.columns:
                    active = (
                        df_part_f.groupby(["user_email"])
                        .agg(
                            name=("name", "first"),
                            company=("company", "first"),
                            total_attendances=("webinar_id", "count"),
                            unique_sessions=("webinar_id", "nunique"),
                            series_list=("series", lambda x: ", ".join(sorted(x.unique()))),
                        )
                        .reset_index()
                        .sort_values("total_attendances", ascending=False)
                        .head(50)
                    )
                    st.dataframe(
                        active.rename(columns={
                            "user_email":        "Email",
                            "name":              "Name",
                            "company":           "Company",
                            "total_attendances": "Total Attendances",
                            "unique_sessions":   "Unique Sessions",
                            "series_list":       "Series Attended",
                        }),
                        use_container_width=True,
                        hide_index=True,
                    )
            else:
                st.subheader(f"Search results ({len(df_search)} rows)")
                show_cols = [c for c in ["name", "user_email", "company", "series", "session_date", "webinar_topic"] if c in df_search.columns]
                st.dataframe(
                    df_search[show_cols].rename(columns={
                        "name": "Name", "user_email": "Email", "company": "Company",
                        "series": "Series", "session_date": "Date", "webinar_topic": "Topic",
                    }).sort_values("Date", ascending=False),
                    use_container_width=True,
                    hide_index=True,
                )

    # ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    # TAB 6 â RAW DATA
    # ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    with tab_raw:
        st.subheader("Webinars")
        if not df_wb_f.empty:
            raw_wb_cols = [c for c in ["session_date", "month_label", "series", "topic", "id", "join_url", "duration"] if c in df_wb_f.columns]
            st.dataframe(
                df_wb_f[raw_wb_cols].rename(columns={
                    "session_date": "Date",
                    "month_label":  "Month",
                    "series":       "Series",
                    "topic":        "Topic",
                    "id":           "Webinar ID",
                    "join_url":     "Link",
                    "duration":     "Duration (min)",
                }).sort_values("Date", ascending=False),
                use_container_width=True,
                hide_index=True,
            )

        st.subheader("All Participants")
        if not df_part_f.empty:
            raw_p_cols = [c for c in ["session_date", "series", "name", "user_email", "company", "webinar_topic", "join_url"] if c in df_part_f.columns]
            st.dataframe(
                df_part_f[raw_p_cols].rename(columns={
                    "session_date":  "Date",
                    "series":        "Series",
                    "name":          "Name",
                    "user_email":    "Email",
                    "company":       "Company",
                    "webinar_topic": "Topic",
                    "join_url":      "Webinar Link",
                }).sort_values("Date", ascending=False),
                use_container_width=True,
                hide_index=True,
            )
            st.caption(
                f"{len(df_part_f):,} rows  |  "
                f"{df_part_f['user_email'].nunique() if 'user_email' in df_part_f.columns else '-'} unique members"
            )


# ââ Auth flow & app entry point âââââââââââââââââââââââââââââââââââââââââââââââ

def main():
    # Handle OAuth callback
    query_params = st.query_params
    if "code" in query_params and "token_data" not in st.session_state:
        code = query_params["code"]
        try:
            token_data = exchange_code(code)
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
        st.link_button("Connect Zoom Account", get_auth_url(), use_container_width=False)
        return

    # Sidebar disconnect button
    with st.sidebar:
        st.markdown("---")
        if st.button("Disconnect Zoom"):
            for key in ["token_data", "token_expires_at"]:
                st.session_state.pop(key, None)
            st.rerun()

    render_dashboard()


if __name__ == "__main__":
    main()
"""
Digbi Health — Group Coaching Dashboard
Zoom Webinars API · Streamlit Cloud
"""

import os
import urllib.parse
import requests
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, date

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

# ── The 7 recurring Group Coaching series ────────────────────────────────────
COACHING_SERIES = [
    "Orientation + Eat Smart [Employer]",
    "Orientation + Eat Smart [Solera]",
    "How to Read Gene & Gut Kit",
    "How to Read Gut Kit",
    "Living Well with GLP-1",
    "Fine Tuning (2-4.99% WL)",
    "Thriving with IBS",
]

SERIES_COLORS = {
    "Orientation + Eat Smart [Employer]": "#1f77b4",
    "Orientation + Eat Smart [Solera]":   "#ff7f0e",
    "How to Read Gene & Gut Kit":         "#2ca02c",
    "How to Read Gut Kit":                "#d62728",
    "Living Well with GLP-1":             "#9467bd",
    "Fine Tuning (2-4.99% WL)":           "#8c564b",
    "Thriving with IBS":                  "#e377c2",
    "Other":                              "#7f7f7f",
}


def map_to_series(topic: str) -> str:
    """Map a raw webinar topic string to one of the 7 coaching series."""
    if not isinstance(topic, str):
        return "Other"
    t = topic.lower()
    # Solera must come before generic Employer check
    if "solera" in t and ("orientation" in t or "eat smart" in t):
        return "Orientation + Eat Smart [Solera]"
    if ("orientation" in t or "eat smart" in t) and "employer" in t:
        return "Orientation + Eat Smart [Employer]"
    if "gene" in t and "gut" in t:
        return "How to Read Gene & Gut Kit"
    if "gut kit" in t or ("read" in t and "gut" in t):
        return "How to Read Gut Kit"
    if "glp" in t:
        return "Living Well with GLP-1"
    if "fine" in t and ("tun" in t or "wl" in t or "4.99" in t or "4." in t):
        return "Fine Tuning (2-4.99% WL)"
    if "ibs" in t or "irritable" in t:
        return "Thriving with IBS"
    return "Other"


def extract_company(email: str) -> str:
    """Infer company name from email domain."""
    personal = {
        "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com",
        "aol.com", "protonmail.com", "live.com", "me.com", "msn.com",
        "googlemail.com", "ymail.com", "mail.com",
    }
    if not isinstance(email, str) or "@" not in email:
        return "Unknown"
    domain = email.split("@")[-1].lower().strip()
    if domain in personal:
        return "Personal Email"
    parts = domain.split(".")
    return parts[-2].title() if len(parts) >= 2 else domain.title()


def fmt_month(ym: str) -> str:
    """Convert 'YYYY-MM' to 'Jan 2026'."""
    try:
        return datetime.strptime(ym, "%Y-%m").strftime("%b %Y")
    except Exception:
        return ym


def parse_month(label: str) -> str:
    """Convert 'Jan 2026' to 'YYYY-MM' for sorting."""
    try:
        return datetime.strptime(label, "%b %Y").strftime("%Y-%m")
    except Exception:
        return label


# ── OAuth helpers ─────────────────────────────────────────────────────────────

def get_auth_url() -> str:
    params = {
        "response_type": "code",
        "client_id":     CLIENT_ID,
        "redirect_uri":  REDIRECT_URI,
    }
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
def fetch_webinars(user_id: str, from_date: str, to_date: str) -> list:
    """Fetch past webinars for a user within date range."""
    webinars = []
    next_page = None
    while True:
        params = {"type": "past", "from": from_date, "to": to_date, "page_size": 300}
        if next_page:
            params["next_page_token"] = next_page
        r = requests.get(
            f"{ZOOM_API_BASE}/users/{user_id}/webinars",
            headers=get_headers(),
            params=params,
        )
        if r.status_code != 200:
            break
        data = r.json()
        webinars.extend(data.get("webinars", []))
        next_page = data.get("next_page_token")
        if not next_page:
            break
    return webinars


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_participants(webinar_id: str) -> list:
    """Fetch attendees for a past webinar."""
    participants = []
    next_page = None
    while True:
        params = {"page_size": 300}
        if next_page:
            params["next_page_token"] = next_page
        r = requests.get(
            f"{ZOOM_API_BASE}/past_webinars/{webinar_id}/participants",
            headers=get_headers(),
            params=params,
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
    default_from = today - timedelta(days=365)
    from_date    = st.sidebar.date_input("From", value=default_from)
    to_date      = st.sidebar.date_input("To",   value=today)

    if from_date > to_date:
        st.sidebar.error("'From' must be before 'To'.")
        return

    # ── Load data ─────────────────────────────────────────────────────────────
    with st.spinner("Loading webinars..."):
        user_id  = get_user_id()
        webinars = fetch_webinars(user_id, str(from_date), str(to_date))

    if not webinars:
        st.warning("No webinars found in this date range.")
        return

    # Build participant DataFrame
    all_participants = []
    progress = st.progress(0, text="Loading participant data...")
    for i, wb in enumerate(webinars):
        pcts   = fetch_participants(wb["id"])
        series = map_to_series(wb.get("topic", ""))
        for p in pcts:
            p["webinar_id"]    = wb["id"]
            p["webinar_topic"] = wb.get("topic", "Unknown")
            p["series"]        = series
            p["session_date"]  = wb.get("start_time", "")[:10]
            p["session_month"] = wb.get("start_time", "")[:7]   # YYYY-MM
            p["join_url"]      = wb.get("join_url", "")
            p["company"]       = extract_company(p.get("user_email", ""))
        all_participants.extend(pcts)
        progress.progress(
            (i + 1) / len(webinars),
            text=f"Loading participant data... {i+1}/{len(webinars)}"
        )
    progress.empty()

    df_wb   = pd.DataFrame(webinars)
    df_part = pd.DataFrame(all_participants) if all_participants else pd.DataFrame()

    # Enrich webinar DataFrame
    if not df_wb.empty:
        df_wb["series"]        = df_wb["topic"].apply(map_to_series)
        df_wb["session_date"]  = pd.to_datetime(df_wb["start_time"], errors="coerce").dt.date
        df_wb["session_month"] = (
            pd.to_datetime(df_wb["start_time"], errors="coerce")
            .dt.to_period("M").astype(str)
        )
        df_wb["month_label"]   = df_wb["session_month"].apply(fmt_month)
        if "join_url" not in df_wb.columns:
            df_wb["join_url"] = ""

    # ── Sidebar: filters ──────────────────────────────────────────────────────
    st.sidebar.header("Filters")

    all_series = sorted(df_wb["series"].unique().tolist()) if not df_wb.empty else []
    sel_series = st.sidebar.multiselect(
        "Coaching Series",
        options=all_series,
        default=[],
        placeholder="All series",
    )

    # Month options as "Jan 2026" etc.
    raw_months   = sorted(df_wb["session_month"].unique().tolist()) if not df_wb.empty else []
    month_labels = [fmt_month(m) for m in raw_months]
    sel_month_labels = st.sidebar.multiselect(
        "Month",
        options=month_labels,
        default=[],
        placeholder="All months",
    )
    sel_months = [parse_month(lbl) for lbl in sel_month_labels]

    all_companies = []
    if not df_part.empty and "company" in df_part.columns:
        all_companies = sorted(df_part["company"].dropna().unique().tolist())
    sel_companies = st.sidebar.multiselect(
        "Company",
        options=all_companies,
        default=[],
        placeholder="All companies",
    )

    # Apply filters
    mask_wb = pd.Series([True] * len(df_wb), index=df_wb.index)
    if sel_series:
        mask_wb &= df_wb["series"].isin(sel_series)
    if sel_months:
        mask_wb &= df_wb["session_month"].isin(sel_months)
    df_wb_f = df_wb[mask_wb].copy()

    if not df_part.empty:
        mask_p = pd.Series([True] * len(df_part), index=df_part.index)
        if sel_series:
            mask_p &= df_part["series"].isin(sel_series)
        if sel_months:
            mask_p &= df_part["session_month"].isin(sel_months)
        if sel_companies:
            mask_p &= df_part["company"].isin(sel_companies)
        df_part_f = df_part[mask_p].copy()
    else:
        df_part_f = pd.DataFrame()

    # ── Top-level KPI strip ───────────────────────────────────────────────────
    st.title("Digbi Health - Group Coaching Dashboard")
    if sel_series or sel_months or sel_companies:
        parts = []
        if sel_series:       parts.append(f"Series: {', '.join(sel_series)}")
        if sel_month_labels: parts.append(f"Months: {', '.join(sel_month_labels)}")
        if sel_companies:    parts.append(f"Companies: {', '.join(sel_companies)}")
        st.caption("Filtered by: " + " | ".join(parts))

    k1, k2, k3, k4, k5 = st.columns(5)
    total_sessions   = len(df_wb_f)
    total_attendees  = len(df_part_f)
    unique_members   = df_part_f["user_email"].nunique() if not df_part_f.empty and "user_email" in df_part_f.columns else 0
    unique_companies = df_part_f["company"].nunique()    if not df_part_f.empty and "company"    in df_part_f.columns else 0
    avg_per_session  = round(total_attendees / total_sessions, 1) if total_sessions else 0

    k1.metric("Sessions",        total_sessions)
    k2.metric("Total Attendees", total_attendees)
    k3.metric("Unique Members",  unique_members)
    k4.metric("Companies",       unique_companies)
    k5.metric("Avg / Session",   avg_per_session)

    st.markdown("---")

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab_overview, tab_series, tab_company, tab_month, tab_participants, tab_raw = st.tabs([
        "Overview",
        "By Series",
        "By Company",
        "By Month",
        "Participants",
        "Raw Data",
    ])

    # ════════════════════════════════════════════════════════════════════════
    # TAB 1 — OVERVIEW
    # ════════════════════════════════════════════════════════════════════════
    with tab_overview:
        if df_wb_f.empty:
            st.info("No sessions match the current filters.")
        else:
            col_a, col_b = st.columns(2)

            with col_a:
                sess_by_series = (
                    df_wb_f.groupby("series")
                    .size()
                    .reset_index(name="sessions")
                    .sort_values("sessions", ascending=True)
                )
                fig = px.bar(
                    sess_by_series,
                    x="sessions", y="series", orientation="h",
                    title="Sessions per Coaching Series",
                    color="series",
                    color_discrete_map=SERIES_COLORS,
                    labels={"series": "", "sessions": "Sessions"},
                )
                fig.update_layout(showlegend=False, height=350)
                st.plotly_chart(fig, use_container_width=True)

            with col_b:
                if not df_part_f.empty:
                    att_by_series = (
                        df_part_f.groupby("series")
                        .size()
                        .reset_index(name="attendees")
                        .sort_values("attendees", ascending=True)
                    )
                    fig2 = px.bar(
                        att_by_series,
                        x="attendees", y="series", orientation="h",
                        title="Total Attendees per Coaching Series",
                        color="series",
                        color_discrete_map=SERIES_COLORS,
                        labels={"series": "", "attendees": "Attendees"},
                    )
                    fig2.update_layout(showlegend=False, height=350)
                    st.plotly_chart(fig2, use_container_width=True)

            if not df_part_f.empty and "session_month" in df_part_f.columns:
                st.subheader("Attendance Trend by Month")
                trend = (
                    df_part_f.groupby(["session_month", "series"])
                    .size()
                    .reset_index(name="attendees")
                )
                trend["month_label"] = trend["session_month"].apply(fmt_month)
                trend_sorted = trend.sort_values("session_month")
                fig3 = px.line(
                    trend_sorted,
                    x="month_label", y="attendees", color="series",
                    title="Monthly Attendance by Coaching Series",
                    color_discrete_map=SERIES_COLORS,
                    markers=True,
                    labels={"month_label": "Month", "attendees": "Attendees", "series": "Series"},
                )
                fig3.update_layout(height=420, xaxis_tickangle=-30)
                st.plotly_chart(fig3, use_container_width=True)

    # ════════════════════════════════════════════════════════════════════════
    # TAB 2 — BY SERIES
    # ════════════════════════════════════════════════════════════════════════
    with tab_series:
        if df_wb_f.empty:
            st.info("No sessions match the current filters.")
        else:
            series_list   = sorted(df_wb_f["series"].unique().tolist())
            chosen_series = st.selectbox("Select a series to inspect:", series_list)

            df_s   = df_wb_f[df_wb_f["series"] == chosen_series].copy()
            df_p_s = df_part_f[df_part_f["series"] == chosen_series].copy() if not df_part_f.empty else pd.DataFrame()

            s1, s2, s3, s4 = st.columns(4)
            s1.metric("Sessions",       len(df_s))
            s2.metric("Total Attendees", len(df_p_s))
            s3.metric("Unique Members",  df_p_s["user_email"].nunique() if not df_p_s.empty and "user_email" in df_p_s.columns else 0)
            s4.metric("Avg / Session",   round(len(df_p_s) / len(df_s), 1) if len(df_s) else 0)

            col1, col2 = st.columns(2)

            with col1:
                if not df_p_s.empty and "session_date" in df_p_s.columns:
                    att_date = (
                        df_p_s.groupby("session_date")
                        .size()
                        .reset_index(name="attendees")
                        .sort_values("session_date")
                    )
                    fig = px.bar(
                        att_date, x="session_date", y="attendees",
                        title=f"Attendance Per Session",
                        labels={"session_date": "Date", "attendees": "Attendees"},
                        color_discrete_sequence=[SERIES_COLORS.get(chosen_series, "#1f77b4")],
                    )
                    fig.update_layout(height=300, xaxis_tickangle=-30)
                    st.plotly_chart(fig, use_container_width=True)

            with col2:
                if not df_p_s.empty and "company" in df_p_s.columns:
                    top_co = (
                        df_p_s[df_p_s["company"] != "Personal Email"]
                        .groupby("company")
                        .size()
                        .reset_index(name="attendees")
                        .sort_values("attendees", ascending=False)
                        .head(10)
                    )
                    fig2 = px.bar(
                        top_co.sort_values("attendees"),
                        x="attendees", y="company", orientation="h",
                        title="Top Companies",
                        labels={"company": "", "attendees": "Attendees"},
                        color_discrete_sequence=[SERIES_COLORS.get(chosen_series, "#1f77b4")],
                    )
                    fig2.update_layout(height=300)
                    st.plotly_chart(fig2, use_container_width=True)

            # Session log with webinar links
            st.subheader("Session Log")
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
                    link    = row.get("join_url", "")
                    d_str   = str(row.get("session_date", ""))
                    topic   = row.get("topic", "")
                    att     = row.get("attendees", 0)
                    month_l = fmt_month(str(row.get("session_month", ""))[:7]) if row.get("session_month") else ""
                    if link:
                        st.markdown(f"**{d_str}** ({month_l}) &nbsp; {topic} &nbsp;&nbsp; Attendees: **{att}** &nbsp;&nbsp; [Webinar Link]({link})")
                    else:
                        st.markdown(f"**{d_str}** ({month_l}) &nbsp; {topic} &nbsp;&nbsp; Attendees: **{att}**")

    # ════════════════════════════════════════════════════════════════════════
    # TAB 3 — BY COMPANY
    # ════════════════════════════════════════════════════════════════════════
    with tab_company:
        if df_part_f.empty:
            st.info("No participant data available.")
        else:
            company_summary = (
                df_part_f[df_part_f["company"] != "Personal Email"]
                .groupby("company")
                .agg(
                    total_attendances=("user_email", "count"),
                    unique_members=("user_email", "nunique"),
                    series_attended=("series", lambda x: len(x.unique())),
                )
                .reset_index()
                .sort_values("total_attendances", ascending=False)
            )

            st.subheader(f"Company Attendance Summary  —  {len(company_summary)} companies")
            st.dataframe(
                company_summary.rename(columns={
                    "company":           "Company",
                    "total_attendances": "Total Attendances",
                    "unique_members":    "Unique Members",
                    "series_attended":   "Series Attended",
                }),
                use_container_width=True,
                hide_index=True,
            )

            top15 = company_summary.head(15).sort_values("total_attendances")
            fig = px.bar(
                top15,
                x="total_attendances", y="company", orientation="h",
                title="Top 15 Companies by Total Attendances",
                labels={"company": "", "total_attendances": "Attendances"},
                color="series_attended",
                color_continuous_scale="Blues",
            )
            fig.update_layout(height=450)
            st.plotly_chart(fig, use_container_width=True)

            st.markdown("---")
            st.subheader("Company Deep-Dive")
            all_cos    = ["(Select a company)"] + company_summary["company"].tolist()
            chosen_co  = st.selectbox("Select company:", all_cos)

            if chosen_co != "(Select a company)":
                df_co = df_part_f[df_part_f["company"] == chosen_co].copy()

                c1, c2, c3 = st.columns(3)
                c1.metric("Total Attendances", len(df_co))
                c2.metric("Unique Members",    df_co["user_email"].nunique() if "user_email" in df_co.columns else 0)
                c3.metric("Series Attended",   df_co["series"].nunique()     if "series"     in df_co.columns else 0)

                col_l, col_r = st.columns(2)
                with col_l:
                    series_bd = df_co.groupby("series").size().reset_index(name="attendances")
                    fig_co = px.pie(
                        series_bd, values="attendances", names="series",
                        title=f"{chosen_co} — Attendance by Series",
                        color="series", color_discrete_map=SERIES_COLORS,
                    )
                    fig_co.update_layout(height=300)
                    st.plotly_chart(fig_co, use_container_width=True)

                with col_r:
                    monthly_co = (
                        df_co.groupby("session_month")
                        .size().reset_index(name="attendances")
                        .sort_values("session_month")
                    )
                    monthly_co["month_label"] = monthly_co["session_month"].apply(fmt_month)
                    fig_m = px.bar(
                        monthly_co, x="month_label", y="attendances",
                        title=f"{chosen_co} — Monthly Attendance",
                        labels={"month_label": "Month", "attendances": "Attendances"},
                    )
                    fig_m.update_layout(height=300, xaxis_tickangle=-30)
                    st.plotly_chart(fig_m, use_container_width=True)

                st.subheader(f"Members from {chosen_co}")
                member_cols = [c for c in ["name", "user_email", "series", "session_date"] if c in df_co.columns]
                st.dataframe(
                    df_co[member_cols].rename(columns={
                        "name": "Name", "user_email": "Email",
                        "series": "Series", "session_date": "Date",
                    }).sort_values("Date", ascending=False),
                    use_container_width=True,
                    hide_index=True,
                )

    # ════════════════════════════════════════════════════════════════════════
    # TAB 4 — BY MONTH
    # ════════════════════════════════════════════════════════════════════════
    with tab_month:
        if df_part_f.empty:
            st.info("No participant data available.")
        else:
            monthly_summary = (
                df_part_f.groupby("session_month")
                .agg(
                    sessions=("webinar_id", "nunique"),
                    attendances=("user_email", "count"),
                    unique_members=("user_email", "nunique"),
                    companies=("company", "nunique"),
                )
                .reset_index()
                .sort_values("session_month", ascending=False)
            )
            monthly_summary["Month"] = monthly_summary["session_month"].apply(fmt_month)

            st.subheader("Monthly Summary")
            st.dataframe(
                monthly_summary[["Month", "sessions", "attendances", "unique_members", "companies"]].rename(columns={
                    "sessions":       "Sessions",
                    "attendances":    "Total Attendances",
                    "unique_members": "Unique Members",
                    "companies":      "Companies",
                }),
                use_container_width=True,
                hide_index=True,
            )

            # Series x Month heatmap
            st.subheader("Series x Month Heatmap")
            heat = (
                df_part_f.groupby(["series", "session_month"])
                .size().reset_index(name="attendances")
            )
            heat["month_label"] = heat["session_month"].apply(fmt_month)
            pivot = heat.pivot_table(
                index="series", columns="month_label",
                values="attendances", fill_value=0
            )
            sorted_cols = sorted(pivot.columns, key=lambda x: parse_month(x))
            pivot = pivot[sorted_cols]
            fig_h = px.imshow(
                pivot,
                text_auto=True,
                color_continuous_scale="Blues",
                title="Attendances per Series per Month",
                labels={"x": "Month", "y": "Series", "color": "Attendances"},
            )
            fig_h.update_layout(height=400)
            st.plotly_chart(fig_h, use_container_width=True)

            # Month drill-down
            st.markdown("---")
            st.subheader("Month Drill-Down")
            month_options = ["(Select a month)"] + [
                fmt_month(m)
                for m in sorted(df_part_f["session_month"].unique().tolist(), reverse=True)
            ]
            chosen_month_lbl = st.selectbox("Select month:", month_options)

            if chosen_month_lbl != "(Select a month)":
                chosen_month_raw = parse_month(chosen_month_lbl)
                df_m    = df_part_f[df_part_f["session_month"] == chosen_month_raw].copy()
                df_wb_m = df_wb_f[df_wb_f["session_month"]    == chosen_month_raw].copy()

                m1, m2, m3 = st.columns(3)
                m1.metric("Sessions",        len(df_wb_m))
                m2.metric("Attendances",     len(df_m))
                m3.metric("Unique Members",  df_m["user_email"].nunique() if "user_email" in df_m.columns else 0)

                st.subheader(f"Sessions in {chosen_month_lbl}")
                for _, row in df_wb_m.sort_values("session_date").iterrows():
                    wb_id  = row.get("id", "")
                    topic  = row.get("topic", "")
                    s_date = str(row.get("session_date", ""))
                    series = row.get("series", "")
                    link   = row.get("join_url", "")
                    n_att  = len(df_m[df_m["webinar_id"] == wb_id]) if not df_m.empty else 0
                    if link:
                        st.markdown(f"**{s_date}** &nbsp; {series} &nbsp;&nbsp; Attendees: **{n_att}** &nbsp;&nbsp; [Webinar Link]({link})")
                    else:
                        st.markdown(f"**{s_date}** &nbsp; {series} &nbsp;&nbsp; Attendees: **{n_att}**")

    # ════════════════════════════════════════════════════════════════════════
    # TAB 5 — PARTICIPANTS
    # ════════════════════════════════════════════════════════════════════════
    with tab_participants:
        if df_part_f.empty:
            st.info("No participant data available.")
        else:
            search_q = st.text_input("Search by name or email", placeholder="e.g. Jane or jane@company.com")

            df_search = df_part_f.copy()
            if search_q:
                q    = search_q.lower()
                name_col  = df_search.get("name",       pd.Series([""] * len(df_search), index=df_search.index))
                email_col = df_search.get("user_email", pd.Series([""] * len(df_search), index=df_search.index))
                mask = (
                    name_col.str.lower().str.contains(q, na=False)
                    | email_col.str.lower().str.contains(q, na=False)
                )
                df_search = df_search[mask]

            if not search_q:
                st.subheader("Most Active Participants")
                if "user_email" in df_part_f.columns:
                    active = (
                        df_part_f.groupby(["user_email"])
                        .agg(
                            name=("name", "first"),
                            company=("company", "first"),
                            total_attendances=("webinar_id", "count"),
                            unique_sessions=("webinar_id", "nunique"),
                            series_list=("series", lambda x: ", ".join(sorted(x.unique()))),
                        )
                        .reset_index()
                        .sort_values("total_attendances", ascending=False)
                        .head(50)
                    )
                    st.dataframe(
                        active.rename(columns={
                            "user_email":        "Email",
                            "name":              "Name",
                            "company":           "Company",
                            "total_attendances": "Total Attendances",
                            "unique_sessions":   "Unique Sessions",
                            "series_list":       "Series Attended",
                        }),
                        use_container_width=True,
                        hide_index=True,
                    )
            else:
                st.subheader(f"Search results ({len(df_search)} rows)")
                show_cols = [c for c in ["name", "user_email", "company", "series", "session_date", "webinar_topic"] if c in df_search.columns]
                st.dataframe(
                    df_search[show_cols].rename(columns={
                        "name": "Name", "user_email": "Email", "company": "Company",
                        "series": "Series", "session_date": "Date", "webinar_topic": "Topic",
                    }).sort_values("Date", ascending=False),
                    use_container_width=True,
                    hide_index=True,
                )

    # ════════════════════════════════════════════════════════════════════════
    # TAB 6 — RAW DATA
    # ════════════════════════════════════════════════════════════════════════
    with tab_raw:
        st.subheader("Webinars")
        if not df_wb_f.empty:
            raw_wb_cols = [c for c in ["session_date", "month_label", "series", "topic", "id", "join_url", "duration"] if c in df_wb_f.columns]
            st.dataframe(
                df_wb_f[raw_wb_cols].rename(columns={
                    "session_date": "Date",
                    "month_label":  "Month",
                    "series":       "Series",
                    "topic":        "Topic",
                    "id":           "Webinar ID",
                    "join_url":     "Link",
                    "duration":     "Duration (min)",
                }).sort_values("Date", ascending=False),
                use_container_width=True,
                hide_index=True,
            )

        st.subheader("All Participants")
        if not df_part_f.empty:
            raw_p_cols = [c for c in ["session_date", "series", "name", "user_email", "company", "webinar_topic", "join_url"] if c in df_part_f.columns]
            st.dataframe(
                df_part_f[raw_p_cols].rename(columns={
                    "session_date":  "Date",
                    "series":        "Series",
                    "name":          "Name",
                    "user_email":    "Email",
                    "company":       "Company",
                    "webinar_topic": "Topic",
                    "join_url":      "Webinar Link",
                }).sort_values("Date", ascending=False),
                use_container_width=True,
                hide_index=True,
            )
            st.caption(
                f"{len(df_part_f):,} rows  |  "
                f"{df_part_f['user_email'].nunique() if 'user_email' in df_part_f.columns else '-'} unique members"
            )


# ── Auth flow & app entry point ───────────────────────────────────────────────

def main():
    # Handle OAuth callback
    query_params = st.query_params
    if "code" in query_params and "token_data" not in st.session_state:
        code = query_params["code"]
        try:
            token_data = exchange_code(code)
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
        st.link_button("Connect Zoom Account", get_auth_url(), use_container_width=False)
        return

    # Sidebar disconnect button
    with st.sidebar:
        st.markdown("---")
        if st.button("Disconnect Zoom"):
            for key in ["token_data", "token_expires_at"]:
                st.session_state.pop(key, None)
            st.rerun()

    render_dashboard()


if __name__ == "__main__":
    main()
