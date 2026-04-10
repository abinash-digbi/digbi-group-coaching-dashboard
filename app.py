"""
Digbi Health — Group Coaching Dashboard
Standard API Version (Works with your specific Scopes)
"""

import time
import requests
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date, timezone
from zoneinfo import ZoneInfo
from urllib.parse import urlencode, quote

# 1. SETUP
st.set_page_config(page_title="Digbi Analytics", page_icon="🧬", layout="wide")

CLIENT_ID     = st.secrets["ZOOM_CLIENT_ID"]
CLIENT_SECRET = st.secrets["ZOOM_CLIENT_SECRET"]
REDIRECT_URI  = st.secrets["ZOOM_REDIRECT_URI"]
ZOOM_API_BASE = "https://api.zoom.us/v2"

# Exact character-matched titles from your Jan-Apr CSV reports
COACHING_SERIES = [
    "Digbi Health Orientation & How to Eat Smart - Group Coaching for Members",
    "Digbi Health Orientation & How to Eat Smart - Join Our Group Coaching Session",
    "Learn to Read and Apply Your Genetics Nutrition and Gut Monitoring Reports for Better Health",
    "Follow Your Gut Instincts: Understanding Your Gut Microbiome Report",
    "Introducing Digbi Health: An Exclusive Wellness Benefit with access to GLP-1s",
    "Thriving with IBS: A Group Coaching Program for Relief and Empowerment",
    "Fine-Tuning Your Routine: Advanced Tips for Continued Weight Loss"
]

# 2. HELPER FUNCTIONS
def get_auth_url():
    p = {"response_type": "code", "client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI}
    return f"https://zoom.us/oauth/authorize?{urlencode(p)}"

def exchange_code(auth_code):
    r = requests.post("https://zoom.us/oauth/token", params={"grant_type": "authorization_code", "code": auth_code, "redirect_uri": REDIRECT_URI}, auth=(CLIENT_ID, CLIENT_SECRET))
    return r.json()

def safe_encode_uuid(uuid_str):
    if uuid_str.startswith('/') or '//' in uuid_str:
        return quote(quote(uuid_str, safe=''), safe='')
    return uuid_str

def map_to_series(topic_str):
    if not isinstance(topic_str, str): return "Other"
    t = topic_str.strip().lower()
    
    # Exclusion List: Block one-off client webinars
    excluded = ["schreiber", "dexcom", "kehe", "ndphit", "silgan", "okaloosa", "azlgebt", "frp", "evry health", "raght", "mohave", "sscgp", "southern", "weston", "prism", "zachry", "city of fw", "city of fort worth", "aaa", "elbit", "vericast", "dexter", "west fargo", "naebt", "cct"]
    if any(k in t for k in excluded): return "Other"

    if "group coaching for members" in t: return COACHING_SERIES[0]
    if "join our group coaching session" in t: return COACHING_SERIES[1]
    if "genetics nutrition" in t: return COACHING_SERIES[2]
    if "gut instincts" in t or "microbiome report" in t: return COACHING_SERIES[3]
    # April Update: Catching new GLP-1 title
    if "glp-1" in t or "wellness benefit" in t or "living well" in t: return COACHING_SERIES[4]
    if "thriving with ibs" in t: return COACHING_SERIES[5]
    if "fine tuning" in t or "fine-tuning" in t: return COACHING_SERIES[6]
    return "Other"

# 3. DATA FETCHING (Using Standard Endpoints)
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_sessions_standard(token):
    headers = {"Authorization": f"Bearer {token}"}
    results = []
    
    # A. Fetch Past Webinars (Standard List)
    # Note: Standard API usually only returns last 30 days of past sessions
    r_w = requests.get(f"{ZOOM_API_BASE}/users/me/webinars", headers=headers, params={"type": "past", "page_size": 300})
    if r_w.status_code == 200:
        results.extend(r_w.json().get("webinars", []))
    
    # B. Fetch Past Meetings (Your April CSV showed Meetings!)
    r_m = requests.get(f"{ZOOM_API_BASE}/users/me/meetings", headers=headers, params={"type": "past", "page_size": 300})
    if r_m.status_code == 200:
        results.extend(r_m.json().get("meetings", []))
        
    return results

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_participants(uuid, is_webinar, token):
    headers = {"Authorization": f"Bearer {token}"}
    safe_id = safe_encode_uuid(uuid)
    endpoint = f"past_webinars/{safe_id}/participants" if is_webinar else f"past_meetings/{safe_id}/participants"
    r = requests.get(f"{ZOOM_API_BASE}/{endpoint}", headers=headers, params={"page_size": 300})
    return r.json().get("participants", []) if r.status_code == 200 else []

# 4. DASHBOARD UI
def render_dashboard():
    token = st.session_state["token_data"]["access_token"]
    
    with st.spinner("Syncing sessions using Standard API..."):
        all_found = fetch_sessions_standard(token)

    if not all_found:
        st.error("No sessions found. Check if hello@digbihealth.com is the account currently logged in.")
        return

    all_parts = []
    mapped_sessions = []
    now_utc = datetime.now(timezone.utc)

    for item in all_found:
        m_name = map_to_series(item.get("topic", ""))
        item["series_mapped"] = m_name
        mapped_sessions.append(item)
        
        if m_name != "Other":
            # Participant Logic
            is_web = "webinar" in str(item.get("type", "")).lower() or item.get("type") in [5, 6, 9]
            pts = fetch_participants(item["uuid"], is_web, token)
            for p in pts:
                p.update({"series": m_name, "webinar_id": item["id"]})
                all_participants.append(p)
            time.sleep(0.1)

    df_wb = pd.DataFrame(mapped_sessions)
    df_part = pd.DataFrame(all_participants) if all_participants else pd.DataFrame()

    st.title("Digbi Health - Group Coaching Dashboard")
    
    # Summary Table
    st.subheader("Series Performance Breakdown")
    base = pd.DataFrame({"series": COACHING_SERIES})
    counts = df_wb[df_wb["series_mapped"] != "Other"].groupby("series_mapped").size().reset_index(name="Sessions")
    
    if not df_part.empty:
        stats = df_part.groupby("series").agg(Attendees=("user_email", "count"), Unique=("user_email", "nunique")).reset_index()
    else:
        stats = pd.DataFrame(columns=["series", "Attendees", "Unique"])

    merged = pd.merge(base, counts, left_on="series", right_on="series_mapped", how="left").fillna(0)
    merged = pd.merge(merged, stats, on="series", how="left").fillna(0)
    
    st.dataframe(merged[["series", "Sessions", "Attendees", "Unique"]], use_container_width=True, hide_index=True)

    with st.expander("Debug: Sessions Found"):
        st.dataframe(df_wb[["start_time", "topic", "series_mapped", "id"]].sort_values("start_time", ascending=False))

# 5. ENTRY
if "token_data" not in st.session_state:
    if "code" in st.query_params:
        st.session_state["token_data"] = exchange_code(st.query_params["code"])
        st.rerun()
    st.title("Login to Digbi Zoom")
    st.markdown(f'<a href="{get_auth_url()}" target="_self" style="background:#FF4B4B;color:white;padding:12px 24px;text-decoration:none;border-radius:6px;font-weight:bold;display:inline-block;">Connect Zoom Account</a>', unsafe_allow_html=True)
else:
    render_dashboard()