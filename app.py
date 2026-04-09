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
from datetime import datetime, timedelta, date, timezone
from zoneinfo import ZoneInfo
from dateutil.relativedelta import relativedelta

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="Digbi Group Coaching", page_icon="🧬", layout="wide")

# ── Zoom credentials ─────────────────────────────────────────────────────────
CLIENT_ID     = st.secrets["ZOOM_CLIENT_ID"]
CLIENT_SECRET = st.secrets["ZOOM_CLIENT_SECRET"]
REDIRECT_URI  = st.secrets["ZOOM_REDIRECT_URI"]
ZOOM_API_BASE = "https://api.zoom.us/v2"

# ── The 7 Core Series (Character-Matched from your CSV Reports) ──────────────
COACHING_SERIES = [
    "Digbi Health Orientation & How to Eat Smart - Group Coaching for Members",
    "Digbi Health Orientation & How to Eat Smart - Join Our Group Coaching Session",
    "Learn to Read and Apply Your Genetics Nutrition and Gut Monitoring Reports for Better Health",
    "Follow Your Gut Instincts: Understanding Your Gut Microbiome Report",
    "Introducing Digbi Health: An Exclusive Wellness Benefit with access to GLP-1s",
    "Thriving with IBS Group Coaching",
    "Fine Tuning Group Coaching (2-4.99% WL)"
]

# ── Robust Mapping Logic ─────────────────────────────────────────────────────
def map_to_series(topic: str) -> str:
    if not isinstance(topic, str): return "Other"
    t_lower = topic.strip().lower()

    # 1. Company Exclusion List (As requested)
    excluded = ["schreiber", "dexcom", "kehe", "ndphit", "silgan", "okaloosa", "azlgebt", "frp", "evry health", "raght", "mohave", "sscgp", "southern", "weston", "prism", "zachry", "city of fw", "city of fort worth", "aaa", "elbit", "vericast", "dexter", "west fargo", "naebt", "cct"]
    if any(k in t_lower for k in excluded): return "Other"

    # 2. Match based on the official recurring titles
    if "group coaching for members" in t_lower:
        return "Digbi Health Orientation & How to Eat Smart - Group Coaching for Members"
    if "join our group coaching session" in t_lower:
        return "Digbi Health Orientation & How to Eat Smart - Join Our Group Coaching Session"
    if "genetics nutrition" in t_lower:
        return "Learn to Read and Apply Your Genetics Nutrition and Gut Monitoring Reports for Better Health"
    if "gut instincts" in t_lower or "microbiome report" in t_lower:
        return "Follow Your Gut Instincts: Understanding Your Gut Microbiome Report"
    if "glp-1" in t_lower or "exclusive wellness benefit" in t_lower:
        return "Introducing Digbi Health: An Exclusive Wellness Benefit with access to GLP-1s"
    if "thriving with ibs" in t_lower:
        return "Thriving with IBS Group Coaching"
    if "fine tuning" in t_lower:
        return "Fine Tuning Group Coaching (2-4.99% WL)"
    
    return "Other"

# ── API Helpers ──────────────────────────────────────────────────────────────
def get_auth_url():
    params = {"response_type": "code", "client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI}
    return f"https://zoom.us/oauth/authorize?{urllib.parse.urlencode(params)}"

def exchange_code(code):
    r = requests.post("https://zoom.us/oauth/token", params={"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI}, auth=(CLIENT_ID, CLIENT_SECRET))
    return r.json()

def get_headers():
    return {"Authorization": f"Bearer {st.session_state['token_data']['access_token']}"}

def safe_encode_uuid(uuid):
    """Crucial: Encodes UUIDs with slashes so Zoom doesn't return 404."""
    if uuid.startswith('/') or '//' in uuid:
        return urllib.parse.quote(urllib.parse.quote(uuid, safe=''), safe='')
    return uuid

# ── Incremental Data Fetching (Bypasses Zoom's 30-Day limit) ──────────────────
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_incremental_history(start_date, end_date):
    webinars = []
    curr = start_date
    while curr < end_date:
        nxt = min(curr + relativedelta(months=1), end_date)
        params = {"type": "past", "from": curr.strftime("%Y-%m-%d"), "to": nxt.strftime("%Y-%m-%d"), "page_size": 300}
        r = requests.get(f"{ZOOM_API_BASE}/users/me/webinars", headers=get_headers(), params=params)
        if r.status_code == 200:
            webinars.extend(r.json().get("webinars", []))
        curr = nxt + timedelta(days=1)
    
    # Add Upcoming Sessions
    r_up = requests.get(f"{ZOOM_API_BASE}/users/me/webinars", headers=get_headers(), params={"type": "upcoming"})
    if r_up.status_code == 200: webinars.extend(r_up.json().get("webinars", []))
    
    # Deduplicate
    seen = set()
    unique = []
    for w in webinars:
        key = f"{w['id']}_{w['start_time']}"
        if key not in seen: seen.add(key); unique.append(w)
    return unique

# ── Main Rendering Logic ──────────────────────────────────────────────────────
def render_dashboard():
    st.sidebar.header("Filter Settings")
    from_date = st.sidebar.date_input("Start Date", value=date(2026, 1, 1))
    to_date = st.sidebar.date_input("End Date", value=date.today())

    with st.spinner("Fetching full year history month-by-month..."):
        webinars = fetch_incremental_history(from_date, to_date)

    if not webinars:
        st.error("No webinars found for this Zoom account. Check your filters.")
        return

    all_participants = []
    now_utc = datetime.now(timezone.utc)

    for i, wb in enumerate(webinars):
        series = map_to_series(wb.get("topic", ""))
        if series == "Other": continue # Skip company-specific webinars
        
        # Format session date
        start_dt = datetime.fromisoformat(wb["start_time"].replace("Z", "+00:00"))
        session_date = start_dt.astimezone(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")
        wb["series"] = series
        wb["clean_date"] = session_date

        if start_dt < now_utc: # Only fetch attendees for past sessions
            safe_uuid = safe_encode_uuid(wb['uuid'])
            r = requests.get(f"{ZOOM_API_BASE}/past_webinars/{safe_uuid}/participants", headers=get_headers(), params={"page_size": 300})
            if r.status_code == 200:
                for p in r.json().get("participants", []):
                    p.update({"series": series, "webinar_id": wb["id"], "session_date": session_date})
                    all_participants.append(p)
            time.sleep(0.1)

    df_wb = pd.DataFrame(webinars)
    df_part = pd.DataFrame(all_participants)

    st.title("Digbi Health - Group Coaching Dashboard")
    
    # Filter by selected date range
    df_wb_f = df_wb[(df_wb["clean_date"] >= str(from_date)) & (df_wb["clean_date"] <= str(to_date))]
    
    # Create the Summary Table
    base_df = pd.DataFrame({"series": COACHING_SERIES})
    wb_counts = df_wb_f[df_wb_f["series"] != "Other"].groupby("series").size().reset_index(name="Sessions")
    
    if not df_part.empty:
        part_stats = df_part.groupby("series").agg(Total_Attendees=("user_email", "count"), Unique_Members=("user_email", "nunique")).reset_index()
    else:
        part_stats = pd.DataFrame(columns=["series", "Total_Attendees", "Unique_Members"])

    stats_df = pd.merge(base_df, wb_counts, on="series", how="left").fillna(0)
    stats_df = pd.merge(stats_df, part_stats, on="series", how="left").fillna(0)
    
    # Safe Calculation to avoid crashes
    stats_df["Avg Sessions / Attendee"] = stats_df.apply(lambda r: round(r["Total_Attendees"] / r["Unique_Members"], 2) if r["Unique_Members"] > 0 else 0, axis=1)

    st.subheader("Final Data Stats for Core Webinars")
    st.dataframe(stats_df.sort_values("Total_Attendees", ascending=False), use_container_width=True, hide_index=True)

    # Debug Data (Hidden in expander)
    with st.expander("Show Raw Mapping (Debug)"):
        st.write(df_wb_f[["clean_date", "topic", "series"]])

# ── Auth Flow ───────────────────────────────────────────────────────────────
if "token_data" not in st.session_state:
    if "code" in st.query_params:
        st.session_state["token_data"] = exchange_code(st.query_params["code"])
        st.rerun()
    st.title("Connect to Zoom")
    st.markdown(f'<a href="{get_auth_url()}" target="_self" style="background:#FF4B4B;color:white;padding:12px 24px;text-decoration:none;border-radius:6px;font-family:sans-serif;font-weight:bold;">Login to Group Coaching Account</a>', unsafe_allow_html=True)
else:
    render_dashboard()