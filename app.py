"""
Digbi Health — Group Coaching Dashboard
Report API Version: Historical Data Recovery
"""

import time
import requests
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
from urllib.parse import urlencode, quote
from dateutil.relativedelta import relativedelta

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

    # 2. Core Mapping (Matched to your CSV topics)
    if "group coaching for members" in t: return COACHING_SERIES[0]
    if "join our group coaching session" in t: return COACHING_SERIES[1]
    if "genetics nutrition" in t: return COACHING_SERIES[2]
    if "gut instincts" in t or "microbiome report" in t: return COACHING_SERIES[3]
    if "glp-1" in t or "wellness benefit" in t or "living well" in t: return COACHING_SERIES[4]
    if "thriving with ibs" in t: return COACHING_SERIES[5]
    if "fine tuning" in t or "fine-tuning" in t: return COACHING_SERIES[6]
    return "Other"

# 3. REPORT API DATA FETCHING (Bypasses the "Last 30 Days" limit)
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_report_data(target_email, start_date, end_date, token):
    headers = {"Authorization": f"Bearer {token}"}
    all_sessions = []
    
    # Report API requires 1-month chunks
    curr_start = start_date
    while curr_start < end_date:
        curr_end = min(curr_start + relativedelta(months=1), end_date)
        params = {"from": curr_start.strftime("%Y-%m-%d"), "to": curr_end.strftime("%Y-%m-%d"), "page_size": 300}
        
        # We check both Meetings and Webinars reports
        # This is where the 31 sessions are hidden!
        r_w = requests.get(f"{ZOOM_API_BASE}/report/users/{target_email}/webinars", headers=headers, params=params)
        if r_w.status_code == 200: all_sessions.extend(r_w.json().get("webinars", []))
        
        r_m = requests.get(f"{ZOOM_API_BASE}/report/users/{target_email}/meetings", headers=headers, params=params)
        if r_m.status_code == 200: all_sessions.extend(r_m.json().get("meetings", []))
        
        curr_start = curr_end + timedelta(days=1)
            
    return all_sessions

# 4. DASHBOARD UI
def render_dashboard():
    token = st.session_state["token_data"]["access_token"]
    
    # ── Sidebar ──
    st.sidebar.title("Sync Control")
    headers = {"Authorization": f"Bearer {token}"}
    
    # Get user list for admin selection
    r_users = requests.get(f"{ZOOM_API_BASE}/users", headers=headers, params={"page_size": 300})
    user_list = [u['email'] for u in r_users.json().get('users', [])] if r_users.status_code == 200 else ["hello@digbihealth.com"]
    
    default_host = user_list.index("hello@digbihealth.com") if "hello@digbihealth.com" in user_list else 0
    target_user = st.sidebar.selectbox("Select Host", options=user_list, index=default_host)

    sd = st.sidebar.date_input("From", value=date(2026, 1, 1))
    ed = st.sidebar.date_input("To", value=date.today())

    if st.sidebar.button("Log Out"):
        st.session_state.clear()
        st.rerun()

    # ── Main Content ──
    st.title(f"Digbi Health Group Coaching Analytics")
    st.write(f"Showing historical report for: **{target_user}**")
    
    with st.spinner(f"Accessing Zoom Reports API for {target_user}..."):
        sessions = fetch_report_data(target_user, sd, ed, token)

    if not sessions:
        st.error(f"No reports found. This account ({target_user}) might not have 'Report' permissions enabled in Zoom.")
        return

    df = pd.DataFrame(sessions)
    df["series"] = df["topic"].apply(map_to_series)
    df_core = df[df["series"] != "Other"].copy()

    # KPI Row
    k1, k2, k3 = st.columns(3)
    k1.metric("Total Core Sessions", len(df_core))
    k2.metric("Excluded (Client) Sessions", len(df[df["series"] == "Other"]))
    k3.metric("Total Zoom Records Found", len(df))

    # Stats Table
    st.subheader("Series Breakdown")
    base = pd.DataFrame({"series": COACHING_SERIES})
    counts = df_core.groupby("series").size().reset_index(name="Sessions Found")
    merged = pd.merge(base, counts, on="series", how="left").fillna(0)
    
    st.dataframe(merged.sort_values("Sessions Found", ascending=False), use_container_width=True, hide_index=True)

    # Debug Data
    with st.expander("Debug: Every single session title found in report"):
        st.dataframe(df[["start_time", "topic", "series"]].sort_values("start_time", ascending=False))

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