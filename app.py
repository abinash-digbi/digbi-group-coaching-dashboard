import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import urllib.parse

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Digbi Group Coaching Dashboard",
    page_icon="💪",
    layout="wide",
)

# ── Credentials from Streamlit secrets ────────────────────────────────────────
CLIENT_ID     = st.secrets["ZOOM_CLIENT_ID"]
CLIENT_SECRET = st.secrets["ZOOM_CLIENT_SECRET"]
REDIRECT_URI  = st.secrets["ZOOM_REDIRECT_URI"]

ZOOM_AUTH_URL  = "https://zoom.us/oauth/authorize"
ZOOM_TOKEN_URL = "https://zoom.us/oauth/token"
ZOOM_API_BASE  = "https://api.zoom.us/v2"

# ── OAuth helpers ───────────────────────────────────────────────────────────────
def get_auth_url():
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
    }
    return f"{ZOOM_AUTH_URL}?{urllib.parse.urlencode(params)}"

def exchange_code_for_token(code: str) -> dict:
    resp = requests.post(
        ZOOM_TOKEN_URL,
        auth=(CLIENT_ID, CLIENT_SECRET),
        data={
            "grant_type":   "authorization_code",
            "code":         code,
            "redirect_uri": REDIRECT_URI,
        },
    )
    resp.raise_for_status()
    return resp.json()

def refresh_access_token(refresh_token: str) -> dict:
    resp = requests.post(
        ZOOM_TOKEN_URL,
        auth=(CLIENT_ID, CLIENT_SECRET),
        data={
            "grant_type":    "refresh_token",
            "refresh_token": refresh_token,
        },
    )
    resp.raise_for_status()
    return resp.json()

def get_headers() -> dict:
    return {"Authorization": f"Bearer {st.session_state['access_token']}"}

# ── API calls ──────────────────────────────────────────────────────────────────
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_meetings(user_id: str, from_date: str, to_date: str) -> list:
    """Fetch past meetings for a user within date range."""
    meetings = []
    next_page = None
    while True:
        params = {
            "type":       "past",
            "from":       from_date,
            "to":         to_date,
            "page_size":  300,
        }
        if next_page:
            params["next_page_token"] = next_page
        r = requests.get(
            f"{ZOOM_API_BASE}/users/{user_id}/meetings",
            headers=get_headers(),
            params=params,
        )
        if r.status_code != 200:
            break
        data = r.json()
        meetings.extend(data.get("meetings", []))
        next_page = data.get("next_page_token")
        if not next_page:
            break
    return meetings

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_participants(meeting_id: str) -> list:
    """Fetch participants for a past meeting."""
    participants = []
    next_page = None
    while True:
        params = {"page_size": 300}
        if next_page:
            params["next_page_token"] = next_page
        r = requests.get(
            f"{ZOOM_API_BASE}/past_meetings/{meeting_id}/participants",
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

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_user_info() -> dict:
    r = requests.get(f"{ZOOM_API_BASE}/users/me", headers=get_headers())
    r.raise_for_status()
    return r.json()

# ── Token management ───────────────────────────────────────────────────────────
def init_tokens():
    """Handle OAuth code exchange or token refresh on every load."""
    query_params = st.query_params

    # Step 1 — code just returned from Zoom
    if "code" in query_params and "access_token" not in st.session_state:
        with st.spinner("Connecting to Zoom…"):
            tokens = exchange_code_for_token(query_params["code"])
            st.session_state["access_token"]  = tokens["access_token"]
            st.session_state["refresh_token"] = tokens["refresh_token"]
            st.session_state["token_expiry"]  = datetime.now() + timedelta(seconds=tokens["expires_in"])
        st.query_params.clear()
        st.rerun()

    # Step 2 — refresh if near expiry
    if "access_token" in st.session_state:
        expiry = st.session_state.get("token_expiry", datetime.now())
        if datetime.now() >= expiry - timedelta(minutes=5):
            tokens = refresh_access_token(st.session_state["refresh_token"])
            st.session_state["access_token"]  = tokens["access_token"]
            st.session_state["refresh_token"] = tokens.get("refresh_token", st.session_state["refresh_token"])
            st.session_state["token_expiry"]  = datetime.now() + timedelta(seconds=tokens["expires_in"])

# ── Dashboard ──────────────────────────────────────────────────────────────────
def render_dashboard():
    user = fetch_user_info()
    user_id   = user.get("id", "me")
    user_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()

    # ── Sidebar ────────────────────────────────────────────────────────────────
    with st.sidebar:
        st.image("https://digbihealth.com/wp-content/uploads/2022/06/digbi-health-logo.png", width=160)
        st.markdown("---")
        st.markdown(f"**Logged in as:** {user_name}")
        st.markdown("---")

        # Date range picker
        st.subheader("📅 Date Range")
        default_from = datetime.now() - timedelta(days=90)
        date_from = st.date_input("From", value=default_from.date())
        date_to   = st.date_input("To",   value=datetime.now().date())

        # Keyword filter for group coaching sessions
        st.subheader("🔍 Filter Sessions")
        keyword = st.text_input("Session name contains", value="Group Coaching")

        if st.button("🔄 Refresh Data"):
            st.cache_data.clear()
            st.rerun()

        st.caption("Data cached for 30 min")
        st.markdown("---")
        if st.button("🔓 Disconnect Zoom"):
            for k in ["access_token", "refresh_token", "token_expiry"]:
                st.session_state.pop(k, None)
            st.rerun()

    # ── Fetch meetings ─────────────────────────────────────────────────────────
    from_str = date_from.strftime("%Y-%m-%d")
    to_str   = date_to.strftime("%Y-%m-%d")

    with st.spinner("Loading meetings…"):
        meetings = fetch_meetings(user_id, from_str, to_str)

    # Filter by keyword
    if keyword:
        meetings = [m for m in meetings if keyword.lower() in m.get("topic", "").lower()]

    # ── Header ─────────────────────────────────────────────────────────────────
    st.title("💪 Digbi Group Coaching Dashboard")
    st.caption(f"Showing sessions from **{from_str}** to **{to_str}**  |  Filter: *\"{keyword}\"*")

    if not meetings:
        st.warning(f"No sessions found matching '{keyword}' in the selected date range. Try adjusting the filter or date range.")
        return

    # ── Fetch participants for each meeting ────────────────────────────────────
    all_participants = []
    progress = st.progress(0, text="Loading participant data…")
    for i, mtg in enumerate(meetings):
        pcts = fetch_participants(mtg["id"])
        for p in pcts:
            p["meeting_id"]    = mtg["id"]
            p["meeting_topic"] = mtg.get("topic", "Unknown")
            p["meeting_date"]  = mtg.get("start_time", "")[:10]
        all_participants.extend(pcts)
        progress.progress((i + 1) / len(meetings), text=f"Loading participant data… {i+1}/{len(meetings)}")
    progress.empty()

    df_mtg  = pd.DataFrame(meetings)
    df_part = pd.DataFrame(all_participants) if all_participants else pd.DataFrame()

    # Parse dates
    if "start_time" in df_mtg.columns:
        df_mtg["start_dt"] = pd.to_datetime(df_mtg["start_time"], errors="coerce")
        df_mtg["date"]     = df_mtg["start_dt"].dt.date
        df_mtg["month"]    = df_mtg["start_dt"].dt.to_period("M").astype(str)

    # ── KPI tiles ──────────────────────────────────────────────────────────────
    total_sessions   = len(df_mtg)
    total_attendees  = len(df_part) if not df_part.empty else 0
    unique_attendees = df_part["user_email"].nunique() if (not df_part.empty and "user_email" in df_part.columns) else 0
    avg_attendance   = round(total_attendees / total_sessions, 1) if total_sessions > 0 else 0

    # Duration avg
    avg_duration = 0
    if "duration" in df_mtg.columns:
        avg_duration = round(df_mtg["duration"].mean(), 0)

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total Sessions",      f"{total_sessions:,}")
    k2.metric("Total Attendees",     f"{total_attendees:,}")
    k3.metric("Unique Participants", f"{unique_attendees:,}")
    k4.metric("Avg Attendance / Session", f"{avg_attendance:,}")
    k5.metric("Avg Duration (min)",  f"{int(avg_duration)}")

    st.markdown("---")

    # ── Charts ─────────────────────────────────────────────────────────────────
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("📈 Sessions per Month")
        if "month" in df_mtg.columns:
            monthly = df_mtg.groupby("month").size().reset_index(name="Sessions")
            st.bar_chart(monthly.set_index("month"))
        else:
            st.info("No date data available.")

    with col_right:
        st.subheader("👥 Attendance per Session")
        if not df_part.empty and "meeting_topic" in df_part.columns:
            att_by_session = (
                df_part.groupby(["meeting_date", "meeting_topic"])
                .size()
                .reset_index(name="Attendees")
                .sort_values("meeting_date")
            )
            st.bar_chart(att_by_session.set_index("meeting_date")["Attendees"])
        else:
            st.info("No participant data available.")

    st.markdown("---")

    # ── Attendance trend line ──────────────────────────────────────────────────
    if not df_part.empty and "meeting_date" in df_part.columns:
        st.subheader("📊 Attendance Trend Over Time")
        trend = (
            df_part.groupby("meeting_date")
            .size()
            .reset_index(name="Attendees")
            .sort_values("meeting_date")
        )
        st.line_chart(trend.set_index("meeting_date"))
        st.markdown("---")

    # ── Session detail table ───────────────────────────────────────────────────
    st.subheader("📋 Session Details")
    display_cols = [c for c in ["date", "topic", "duration", "start_time"] if c in df_mtg.columns]
    if display_cols:
        df_display = df_mtg[display_cols].copy()
        df_display.columns = [c.replace("_", " ").title() for c in df_display.columns]
        st.dataframe(df_display.sort_values("Date" if "Date" in df_display.columns else df_display.columns[0], ascending=False), use_container_width=True)

    # ── Participant detail table ───────────────────────────────────────────────
    if not df_part.empty:
        st.subheader("🧑‍🤝‍🧑 Participant Details")
        part_cols = [c for c in ["name", "user_email", "meeting_topic", "meeting_date", "duration"] if c in df_part.columns]
        if part_cols:
            df_part_display = df_part[part_cols].copy()
            df_part_display.columns = [c.replace("_", " ").title() for c in df_part_display.columns]
            st.dataframe(df_part_display.sort_values("Meeting Date" if "Meeting Date" in df_part_display.columns else df_part_display.columns[0], ascending=False), use_container_width=True)

        # ── Top recurring participants ─────────────────────────────────────────
        if "user_email" in df_part.columns and "name" in df_part.columns:
            st.subheader("🏆 Most Active Participants")
            top_participants = (
                df_part.groupby(["user_email", "name"])
                .size()
                .reset_index(name="Sessions Attended")
                .sort_values("Sessions Attended", ascending=False)
                .head(10)
            )
            st.dataframe(top_participants, use_container_width=True)

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    init_tokens()

    if "access_token" not in st.session_state:
        # Not authenticated — show login screen
        st.title("💪 Digbi Group Coaching Dashboard")
        st.markdown("### Connect your Zoom account to get started")
        st.markdown(
            "This dashboard pulls your Zoom group coaching sessions and shows "
            "attendance, trends, and participant engagement in real time."
        )
        st.markdown("---")
        auth_url = get_auth_url()
        st.markdown(
            f"""<a href="{auth_url}" target="_self">
            <button style="background-color:#2D8CFF;color:white;border:none;
            padding:12px 28px;font-size:16px;border-radius:6px;cursor:pointer;">
            🔗 Connect Zoom Account
            </button></a>""",
            unsafe_allow_html=True,
        )
        st.info("You'll be redirected to Zoom to authorize the app, then brought back here automatically.")
    else:
        render_dashboard()

if __name__ == "__main__":
    main()
