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
st.set_page_config(
    page_title="Digbi Group Coaching",
    page_icon="🧬",
    layout="wide",
)

# ── Zoom credentials ─────────────────────────────────────────────────────────
CLIENT_ID     = st.secrets["ZOOM_CLIENT_ID"]
CLIENT_SECRET = st.secrets["ZOOM_CLIENT_SECRET"]
REDIRECT_URI  = st.secrets["ZOOM_REDIRECT_URI"]
ZOOM_API_BASE = "https://api.zoom.us/v2"

# ── The 7 Series (Exact Titles from CSVs) ────────────────────────────────────
COACHING_SERIES = [
    "Digbi Health Orientation & How to Eat Smart - Group Coaching for Members",
    "Digbi Health Orientation & How to Eat Smart - Join Our Group Coaching Session",
    "Learn to Read and Apply Your Genetics Nutrition and Gut Monitoring Reports for Better Health",
    "Follow Your Gut Instincts: Understanding Your Gut Microbiome Report",
    "Introducing Digbi Health: An Exclusive Wellness Benefit with access to GLP-1s",
    "Thriving with IBS Group Coaching",
    "Fine Tuning Group Coaching (2-4.99% WL)"
]

# ── Mapping Logic ────────────────────────────────────────────────────────────
def map_to_series(topic: str) -> str:
    if not isinstance(topic, str):
        return "Other"
    
    t_clean = topic.strip()
    t_lower = t_clean.lower()

    # 1. Exclusion Check (Client-specific webinars)
    excluded = ["schreiber", "dexcom", "kehe", "ndphit", "silgan", "okaloosa", "azlgebt", "frp", "evry health", "raght", "mohave", "sscgp", "southern", "weston", "prism", "zachry", "city of fw", "city of fort worth", "aaa", "elbit", "vericast", "dexter", "west fargo", "naebt", "cct"]
    if any(k in t_lower for k in excluded):
        return "Other"

    # 2. Exact Title Matching (Source: Zoom CSV Reports)
    if "group coaching for members" in t_lower:
        return "Digbi Health Orientation & How to Eat Smart - Group Coaching for Members"
    if "join our group coaching session" in t_lower:
        return "Digbi Health Orientation & How to Eat Smart - Join Our Group Coaching Session"
    if "genetics nutrition" in t_lower:
        return "Learn to Read and Apply Your Genetics Nutrition and Gut Monitoring Reports for Better Health"
    if "gut instincts" in t_lower or "microbiome report" in t_lower:
        return "Follow Your Gut Instincts: Understanding Your Gut Microbiome Report"
    if "glp-1" in t_lower or "wellness benefit" in t_lower:
        return "Introducing Digbi Health: An Exclusive Wellness Benefit with access to GLP-1s"
    if "thriving with ibs" in t_lower:
        return "Thriving with IBS Group Coaching"
    if "fine tuning" in t_lower:
        return "Fine Tuning Group Coaching (2-4.99% WL)"
        
    return "Other"

# ── OAuth & API Helpers ──────────────────────────────────────────────────────
def get_auth_url():
    params = {"response_type": "code", "client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI}
    return f"https://zoom.us/oauth/authorize?{urllib.parse.urlencode(params)}"

def exchange_code(code):
    r = requests.post("https://zoom.us/oauth/token", params={"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI}, auth=(CLIENT_ID, CLIENT_SECRET))
    return r.json()

def get_headers():
    token = st.session_state["token_data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}

# ── Month-by-Month Fetching ──────────────────────────────────────────────────
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_webinars_incremental(user_id, start_date, end_date):
    webinars = []
    current_start = start_date
    
    while current_start < end_date:
        current_end = min(current_start + relativedelta(months=1), end_date)
        
        next_page = None
        while True:
            params = {
                "type": "past", 
                "from": current_start.strftime("%Y-%m-%d"), 
                "to": current_end.strftime("%Y-%m-%d"),
                "page_size": 300, 
                "next_page_token": next_page
            }
            r = requests.get(f"{ZOOM_API_BASE}/users/{user_id}/webinars", headers=get_headers(), params=params)
            if r.status_code != 200: break
            data = r.json()
            webinars.extend(data.get("webinars", []))
            next_page = data.get("next_page_token")
            if not next_page: break
            
        current_start = current_end + timedelta(days=1)
    return webinars

# ── Dashboard Rendering ──────────────────────────────────────────────────────
def render_dashboard():
    st.sidebar.header("Date Range")
    from_date = st.sidebar.date_input("From", value=date(2026, 1, 1))
    to_date = st.sidebar.date_input("To", value=date.today())

    with st.spinner("Fetching full history from Zoom..."):
        user_id = requests.get(f"{ZOOM_API_BASE}/users/me", headers=get_headers()).json()["id"]
        webinars = fetch_webinars_incremental(user_id, from_date, to_date)

    if not webinars:
        st.warning("No data found.")
        return

    # Process Attendees
    all_participants = []
    for wb in webinars:
        series = map_to_series(wb.get("topic", ""))
        if series == "Other": continue
        
        # Correctly format date for PST
        pst_time = datetime.fromisoformat(wb["start_time"].replace("Z", "+00:00")).astimezone(ZoneInfo("America/Los_Angeles"))
        
        # Fetch Participants
        r = requests.get(f"{ZOOM_API_BASE}/past_webinars/{wb['uuid']}/participants", headers=get_headers(), params={"page_size": 300})
        if r.status_code == 200:
            for p in r.json().get("participants", []):
                p["series"] = series
                p["webinar_id"] = wb["id"]
                all_participants.append(p)
        time.sleep(0.1) # Rate limit protection

    df_wb = pd.DataFrame(webinars)
    df_wb["series"] = df_wb["topic"].apply(map_to_series)
    df_part = pd.DataFrame(all_participants)

    # ── Overview Table ──
    st.title("Digbi Health - Group Coaching Dashboard")
    
    base_df = pd.DataFrame({"series": COACHING_SERIES})
    wb_stats = df_wb[df_wb["series"] != "Other"].groupby("series").size().reset_index(name="Sessions")
    
    if not df_part.empty:
        part_stats = df_part.groupby("series").agg(
            Total_Attendees=("user_email", "count"),
            Unique_Members=("user_email", "nunique")
        ).reset_index()
    else:
        part_stats = pd.DataFrame(columns=["series", "Total_Attendees", "Unique_Members"])

    stats_df = pd.merge(base_df, wb_stats, on="series", how="left").fillna(0)
    stats_df = pd.merge(stats_df, part_stats, on="series", how="left").fillna(0)
    # Calculate average only where Unique_Members is greater than 0 to avoid ZeroDivisionError
    stats_df["Avg Sessions / Attendee"] = stats_df.apply(
        lambda row: round(row["Total_Attendees"] / row["Unique_Members"], 2) 
        if row["Unique_Members"] > 0 else 0, 
        axis=1
    )    
    st.dataframe(stats_df.sort_values("Total_Attendees", ascending=False), use_container_width=True, hide_index=True)

# ── Main Entry ──
if "token_data" not in st.session_state:
    if "code" in st.query_params:
        st.session_state["token_data"] = exchange_code(st.query_params["code"])
        st.rerun()
    st.title("Connect to Zoom")
    st.markdown(f'<a href="{get_auth_url()}" target="_self">Connect Zoom Account</a>', unsafe_allow_html=True)
else:
    render_dashboard()