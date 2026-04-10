"""
Digbi Health — Group Coaching Dashboard
Logic: Force-Pagination Engine (Targets 31+ Sessions)
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

def map_to_series(topic_str):
    if not isinstance(topic_str, str): return "Other"
    t = topic_str.strip().lower()
    
    # 1. Company Exclusion List
    excluded = ["schreiber", "dexcom", "kehe", "ndphit", "silgan", "okaloosa", "azlgebt", "frp", "evry health", "raght", "mohave", "sscgp", "southern", "weston", "prism", "zachry", "city of fw", "city of fort worth", "aaa", "elbit", "vericast", "dexter", "west fargo", "naebt", "cct"]
    if any(k in t for k in excluded): return "Other"

    # 2. Match Topics (Character Perfect)
    if "group coaching for members" in t: return COACHING_SERIES[0]
    if "join our group coaching session" in t: return COACHING_SERIES[1]
    if "genetics nutrition" in t: return COACHING_SERIES[2]
    if "gut instincts" in t or "microbiome report" in t: return COACHING_SERIES[3]
    # Catching GLP-1 variations
    if "glp-1" in t or "wellness benefit" in t or "living well" in t: return COACHING_SERIES[4]
    if "thriving with ibs" in t: return COACHING_SERIES[5]
    if "fine tuning" in t or "fine-tuning" in t: return COACHING_SERIES[6]
    return "Other"

# 3. FORCE-PAGINATION ENGINE (The key to finding all 31 sessions)
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_full_history_paginated(token):
    headers = {"Authorization": f"Bearer {token}"}
    all_sessions = []
    
    # We fetch both Webinars and Meetings because orientations often switch types
    for endpoint_type in ["webinars", "meetings"]:
        next_page_token = ""
        while True:
            params = {"type": "past", "page_size": 300}
            if next_page_token:
                params["next_page_token"] = next_page_token
            
            r = requests.get(f"{ZOOM_API_BASE}/users/me/{endpoint_type}", headers=headers, params=params)
            
            if r.status_code == 200:
                data = r.json()
                all_sessions.extend(data.get(endpoint_type, []))
                next_page_token = data.get("next_page_token")
                if not next_page_token: break
            else:
                break
    
    # Deduplicate by unique start time and ID
    unique_sessions = []
    seen = set()
    for s in all_sessions:
        key = f"{s['id']}_{s['start_time']}"
        if key not in seen:
            seen.add(key)
            unique_sessions.append(s)
            
    return unique_sessions

# 4. DASHBOARD UI
def render_dashboard():
    # SETTING THE DEFAULT TO JAN 1st IN THE SIDEBAR
    st.sidebar.title("Dashboard Filters")
    sd = st.sidebar.date_input("Filter Start Date", value=date(2026, 1, 1))
    ed = st.sidebar.date_input("Filter End Date", value=date.today())
    
    token = st.session_state["token_data"]["access_token"]
    
    with st.spinner("Force-Paginated Sync: Retrieving all history for hello@digbihealth.com..."):
        all_raw_data = fetch_full_history_paginated(token)

    if not all_raw_data:
        st.error("No data returned. Check account permissions.")
        return

    # Process and Map
    mapped_data = []
    for item in all_raw_data:
        # Convert start_time to date object for filtering
        session_dt = datetime.fromisoformat(item["start_time"].replace("Z", "+00:00")).date()
        
        # Apply Date Filter
        if sd <= session_dt <= ed:
            m_series = map_to_series(item.get("topic", ""))
            item["series_mapped"] = m_series
            item["session_date"] = session_dt
            mapped_data.append(item)

    df = pd.DataFrame(mapped_data)
    df_core = df[df["series_mapped"] != "Other"].copy()

    st.title("Digbi Health - Group Coaching Analytics")
    
    # ── KPIs ──
    k1, k2, k3 = st.columns(3)
    k1.metric("Total Core Sessions", len(df_core))
    k2.metric("Filtered Out (Client/Other)", len(df) - len(df_core))
    k3.metric("Total API Records", len(df))

    # ── SUMMARY TABLE ──
    st.subheader("Performance by Series")
    base = pd.DataFrame({"series": COACHING_SERIES})
    counts = df_core.groupby("series_mapped").size().reset_index(name="Sessions")
    merged = pd.merge(base, counts, left_on="series", right_on="series_mapped", how="left").fillna(0)
    
    st.dataframe(merged[["series", "Sessions"]].sort_values("Sessions", ascending=False), use_container_width=True, hide_index=True)

    # ── DEBUG LOG ──
    with st.expander("View Full Session Log (Debug)"):
        st.write("If you see 'Other' below, it means the title didn't match our core list.")
        st.dataframe(df[["session_date", "topic", "series_mapped"]].sort_values("session_date", ascending=False))

# 5. ENTRY
if "token_data" not in st.session_state:
    if "code" in st.query_params:
        st.session_state["token_data"] = exchange_code(st.query_params["code"])
        st.rerun()
    st.title("Digbi Analytics Login")
    login_url = get_auth_url()
    st.markdown(f'<a href="{login_url}" target="_self" style="background:#FF4B4B;color:white;padding:12px 24px;text-decoration:none;border-radius:6px;font-weight:bold;display:inline-block;">Login to Zoom Account</a>', unsafe_allow_html=True)
else:
    render_dashboard()