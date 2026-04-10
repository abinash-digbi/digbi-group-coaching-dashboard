"""
Digbi Health — Group Coaching Dashboard
Zoom Reports API · Streamlit Cloud
"""

import time
import requests
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date, timezone
from zoneinfo import ZoneInfo
from urllib.parse import urlencode, quote

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="Digbi Group Coaching", page_icon="🧬", layout="wide")

# ── Zoom credentials from secrets ────────────────────────────────────────────
# Ensure these match exactly what is in your Streamlit Secrets
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
    "Thriving with IBS: A Group Coaching Program for Relief and Empowerment",
    "Fine-Tuning Your Routine: Advanced Tips for Continued Weight Loss"
]

# ── HELPER FUNCTIONS (Must be defined before use) ─────────────────────────────

def get_auth_url():
    """Generates the Zoom OAuth URL."""
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI
    }
    return f"https://zoom.us/oauth/authorize?{urlencode(params)}"

def exchange_code(code):
    """Exchanges the authorization code for an access token."""
    r = requests.post(
        "https://zoom.us/oauth/token",
        params={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI
        },
        auth=(CLIENT_ID, CLIENT_SECRET)
    )
    return r.json()

def safe_encode_uuid(uuid):
    """Double encodes Zoom UUIDs that contain slashes to avoid 404 errors."""
    if uuid.startswith('/') or '//' in uuid:
        return quote(quote(uuid, safe=''), safe='')
    return uuid

def map_to_series(topic: str) -> str:
    """Maps Zoom topics to core coaching series and excludes one-off client webinars."""
    if not isinstance(topic, str): return "Other"
    t = topic.strip().lower()

    # 1. Exclusion List (Block one-off client webinars from core stats)
    excluded = ["schreiber", "dexcom", "kehe", "ndphit", "silgan", "okaloosa", "azlgebt", "frp", "evry health", "raght", "mohave", "sscgp", "southern", "weston", "prism", "zachry", "city of fw", "city of fort worth", "aaa", "elbit", "vericast", "dexter", "west fargo", "naebt", "cct"]
    if any(k in t for k in excluded): return "Other"

    # 2. Exact Mapping (Direct from CSV titles)
    if "group coaching for members" in t:
        return "Digbi Health Orientation & How to Eat Smart - Group Coaching for Members"
    if "join our group coaching session" in t:
        return "Digbi Health Orientation & How to Eat Smart - Join Our Group Coaching Session"
    if "genetics nutrition" in t:
        return "Learn to Read and Apply Your Genetics Nutrition and Gut Monitoring Reports for Better Health"
    if "gut instincts" in t or "microbiome report" in t:
        return "Follow Your Gut Instincts: Understanding Your Gut Microbiome Report"
    if "glp-1" in t or "exclusive wellness benefit" in t:
        return "Introducing Digbi Health: An Exclusive Wellness Benefit with access to GLP-1s"
    if "thriving with ibs" in t:
        return "Thriving with IBS: A Group Coaching Program for Relief and Empowerment"
    if "fine tuning" in t or "fine-tuning" in t:
        return "Fine-Tuning Your Routine: Advanced Tips for Continued Weight Loss"
    
    return "Other"

# ── DATA FETCHING (Using Report API for high accuracy) ───────────────────────

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_webinar_report(from_date, to_date, access_token):
    """Fetches historical webinar instances in 30-day chunks."""
    all_instances = []
    headers = {"Authorization": f"Bearer {access_token}"}
    curr_start = from_date
    
    while curr_start < to_date:
        curr_end = min(curr_start + timedelta(days=30), to_date)
        params = {
            "from": curr_start.strftime("%Y-%m-%d"),
            "to": curr_end.strftime("%Y-%m-%d"),
            "page_size": 300
        }
        r = requests.get(f"{ZOOM_API_BASE}/report/users/me/webinars", headers=headers, params=params)
        if r.status_code == 200:
            all_instances.extend(r.json().get("webinars", []))
        curr_start = curr_end + timedelta(days=1)
    return all_instances

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_participants_report(uuid, access_token):
    """Fetches attendee list for a specific webinar instance."""
    headers = {"Authorization": f"Bearer {access_token}"}
    safe_uuid = safe_encode_uuid(uuid)
    r = requests.get(f"{ZOOM_API_BASE}/report/webinars/{safe_uuid}/participants", headers=headers, params={"page_size": 300})
    return r.json().get("participants", []) if r.status_code == 200 else []

# ── DASHBOARD UI ──────────────────────────────────────────────────────────────

def render_dashboard():
    st.sidebar.header("Data Range")
    start_date = st.sidebar.date_input("Start Date", value=date(2026, 1, 1))
    end_date = st.sidebar.date_input("End Date", value=date.today())

    token = st.session_state["token_data"]["access_token"]

    with st.spinner("Syncing data from Zoom Reports..."):
        instances = fetch_webinar_report(start_date, end_date, token)

    if not instances:
        st.info("No webinars found in this date range.")
        return

    all_participants = []
    mapped_sessions = []

    for inst in instances:
        series = map_to_series(inst.get("topic", ""))
        if series == "Other": continue
        
        inst_date = inst["start_time"][:10]
        inst["series"] = series
        mapped_sessions.append(inst)
        
        # Fetch attendees
        pcts = fetch_participants_report(inst["uuid"], token)
        for p in pcts:
            p.update({"series": series, "session_date": inst_date})
            all_participants.append(p)
        time.sleep(0.1)

    df_wb = pd.DataFrame(mapped_sessions)
    df_part = pd.DataFrame(all_participants)

    # ── KPI METRICS ──
    st.title("Digbi Health - Group Coaching Dashboard")
    k1, k2, k3, k4 = st.columns(4)
    total_sessions = len(df_wb)
    total_att = len(df_part)
    unique_mem = df_part["user_email"].nunique() if not df_part.empty else 0
    
    k1.metric("Total Sessions", total_sessions)
    k2.metric("Total Attendees", total_att)
    k3.metric("Unique Members", unique_mem)
    k4.metric("Avg Sessions/Member", round(total_att/unique_mem, 2) if unique_mem > 0 else 0)

    # ── SUMMARY TABLE ──
    st.subheader("Stats for 7 Core Coaching Series")
    base_df = pd.DataFrame({"series": COACHING_SERIES})
    wb_counts = df_wb.groupby("series").size().reset_index(name="Sessions")
    
    if not df_part.empty:
        part_stats = df_part.groupby("series").agg(
            Total_Attendees=("user_email", "count"),
            Unique_Members=("user_email", "nunique")
        ).reset_index()
    else:
        part_stats = pd.DataFrame(columns=["series", "Total_Attendees", "Unique_Members"])

    stats_df = pd.merge(base_df, wb_counts, on="series", how="left").fillna(0)
    stats_df = pd.merge(stats_df, part_stats, on="series", how="left").fillna(0)
    
    # Calculation safe from ZeroDivisionError
    stats_df["Avg Sessions / Attendee"] = stats_df.apply(
        lambda r: round(r["Total_Attendees"]/r["Unique_Members"], 2) if r["Unique_Members"] > 0 else 0, axis=1
    )

    st.dataframe(
        stats_df.rename(columns={"series": "Coaching Series"}).sort_values("Total_Attendees", ascending=False), 
        use_container_width=True, 
        hide_index=True
    )

# ── MAIN APP LOGIC ────────────────────────────────────────────────────────────

if "token_data" not in st.session_state:
    # Handle the OAuth callback
    if "code" in st.query_params:
        st.session_state["token_data"] = exchange_code(st.query_params["code"])
        st.rerun()
    
    # Login Screen
    st.title("Digbi Health Dashboard")
    st.markdown("Please connect the official Zoom account to continue.")
    
    # Link formatted as a button that opens in the SAME TAB
    login_url = get_auth_url()
    st.markdown(
        f'<a href="{login_url}" target="_self" style="background:#FF4B4B;color:white;padding:12px 24px;text-decoration:none;border-radius:6px;font-weight:bold;display:inline-block;">Connect Zoom Account</a>', 
        unsafe_allow_html=True
    )
else:
    # If logged in, show the dashboard
    render_dashboard()