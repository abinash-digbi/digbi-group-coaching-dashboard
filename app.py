"""
Digbi Health — Group Coaching Dashboard
Zoom Reports API (Meetings + Webinars)
"""

import time
import requests
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
from urllib.parse import urlencode, quote

# 1. SETUP
st.set_page_config(page_title="Digbi Group Coaching", page_icon="🧬", layout="wide")

CLIENT_ID     = st.secrets["ZOOM_CLIENT_ID"]
CLIENT_SECRET = st.secrets["ZOOM_CLIENT_SECRET"]
REDIRECT_URI  = st.secrets["ZOOM_REDIRECT_URI"]
ZOOM_API_BASE = "https://api.zoom.us/v2"

# Characters matched exactly from Jan-Apr reports 
COACHING_SERIES = [
    "Digbi Health Orientation & How to Eat Smart - Group Coaching for Members",
    "Digbi Health Orientation & How to Eat Smart - Join Our Group Coaching Session",
    "Learn to Read and Apply Your Genetics Nutrition and Gut Monitoring Reports for Better Health",
    "Follow Your Gut Instincts: Understanding Your Gut Microbiome Report",
    "Introducing Digbi Health: An Exclusive Wellness Benefit with access to GLP-1s",
    "Thriving with IBS: A Group Coaching Program for Relief and Empowerment",
    "Fine-Tuning Your Routine: Advanced Tips for Continued Weight Loss"
]

# 2. MAPPING LOGIC
def map_to_series(topic_str):
    if not isinstance(topic_str, str): return "Other"
    t = topic_str.strip().lower()
    
    # Exclusion List: Block one-off client webinars [cite: 117]
    excluded = ["schreiber", "dexcom", "kehe", "ndphit", "silgan", "okaloosa", "azlgebt", "frp", "evry health", "raght", "mohave", "sscgp", "southern", "weston", "prism", "zachry", "city of fw", "city of fort worth", "aaa", "elbit", "vericast", "dexter", "west fargo", "naebt", "cct"]
    if any(k in t for k in excluded): return "Other"

    # Precise matching based on CSV history 
    if "group coaching for members" in t: return COACHING_SERIES[0]
    if "join our group coaching session" in t: return COACHING_SERIES[1]
    if "genetics nutrition" in t: return COACHING_SERIES[2]
    if "gut instincts" in t or "microbiome report" in t: return COACHING_SERIES[3]
    # Catch both versions of GLP-1 names found in your files 
    if "glp-1" in t or "exclusive wellness benefit" in t or "living well with glp" in t:
        return COACHING_SERIES[4]
    if "thriving with ibs" in t: return COACHING_SERIES[5]
    if "fine tuning" in t or "fine-tuning" in t: return COACHING_SERIES[6]
    return "Other"

# 3. API HELPERS
def get_auth_url():
    payload = {"response_type": "code", "client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI}
    return f"https://zoom.us/oauth/authorize?{urlencode(payload)}"

def exchange_code(auth_code):
    r = requests.post("https://zoom.us/oauth/token", params={"grant_type": "authorization_code", "code": auth_code, "redirect_uri": REDIRECT_URI}, auth=(CLIENT_ID, CLIENT_SECRET))
    return r.json()

def safe_encode_uuid(uuid_str):
    if uuid_str.startswith('/') or '//' in uuid_str:
        return quote(quote(uuid_str, safe=''), safe='')
    return uuid_str

# 4. DATA FETCHING (Checks BOTH Meetings and Webinars)
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_all_reports(start_date, end_date, token):
    results = []
    headers = {"Authorization": f"Bearer {token}"}
    curr = start_date
    while curr < end_date:
        nxt = min(curr + timedelta(days=30), end_date)
        params = {"from": curr.strftime("%Y-%m-%d"), "to": nxt.strftime("%Y-%m-%d"), "page_size": 300}
        
        # A. Check Meeting Report 
        r_m = requests.get(f"{ZOOM_API_BASE}/report/users/me/meetings", headers=headers, params=params)
        if r_m.status_code == 200:
            results.extend(r_m.json().get("meetings", []))
            
        # B. Check Webinar Report 
        r_w = requests.get(f"{ZOOM_API_BASE}/report/users/me/webinars", headers=headers, params=params)
        if r_w.status_code == 200:
            results.extend(r_w.json().get("webinars", []))
            
        curr = nxt + timedelta(days=1)
    return results

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_participants(uuid, is_webinar, token):
    headers = {"Authorization": f"Bearer {token}"}
    safe_id = safe_encode_uuid(uuid)
    path = "webinars" if is_webinar else "meetings"
    r = requests.get(f"{ZOOM_API_BASE}/report/{path}/{safe_id}/participants", headers=headers, params={"page_size": 300})
    return r.json().get("participants", []) if r.status_code == 200 else []

# 5. UI RENDERING
def render_dashboard():
    st.sidebar.header("Date Filters")
    sd = st.sidebar.date_input("Start Date", value=date(2026, 1, 1))
    ed = st.sidebar.date_input("End Date", value=date.today())

    token = st.session_state["token_data"]["access_token"]
    
    with st.spinner("Searching all Meeting and Webinar reports..."):
        instances = fetch_all_reports(sd, ed, token)

    if not instances:
        st.error("No data returned from Zoom.")
        st.write("Logged in as hello@digbihealth.com, but no meeting/webinar history found in this date range.")
        return

    all_parts = []
    found_sessions = []

    for item in instances:
        m_name = map_to_series(item.get("topic", ""))
        if m_name == "Other": continue
        
        item["series"] = m_name
        found_sessions.append(item)
        
        # Determine if it's a webinar or meeting for the correct participant endpoint
        is_web = "webinar" in str(item.get("type", "")).lower() or item.get("type") in [5, 6, 9]
        parts = fetch_participants(item["uuid"], is_web, token)
        
        for p in parts:
            p.update({"series": m_name, "webinar_id": item["id"]})
            all_parts.append(p)
        time.sleep(0.1)

    df_wb = pd.DataFrame(found_sessions)
    df_part = pd.DataFrame(all_parts)

    st.title("Digbi Health - Group Coaching Dashboard")
    
    # KPI Breakdown
    st.subheader("Stats for Core Coaching Series")
    base = pd.DataFrame({"series": COACHING_SERIES})
    counts = df_wb.groupby("series").size().reset_index(name="Sessions")
    
    if not df_part.empty:
        stats = df_part.groupby("series").agg(Attendees=("user_email", "count"), Unique=("user_email", "nunique")).reset_index()
    else:
        stats = pd.DataFrame(columns=["series", "Attendees", "Unique"])

    merged = pd.merge(base, counts, on="series", how="left").fillna(0)
    merged = pd.merge(merged, stats, on="series", how="left").fillna(0)
    merged["Avg Per Session"] = (merged["Attendees"] / merged["Sessions"]).fillna(0).round(1)

    st.dataframe(merged.sort_values("Attendees", ascending=False), use_container_width=True, hide_index=True)

    with st.expander("Debug: Raw Meeting Titles Found"):
        st.write(df_wb[["start_time", "topic", "series"]])

# 6. ENTRY
if "token_data" not in st.session_state:
    if "code" in st.query_params:
        st.session_state["token_data"] = exchange_code(st.query_params["code"])
        st.rerun()
    st.title("Digbi Group Coaching")
    st.markdown(f'<a href="{get_auth_url()}" target="_self" style="background:#FF4B4B;color:white;padding:12px 24px;text-decoration:none;border-radius:6px;font-weight:bold;display:inline-block;">Connect Zoom Account</a>', unsafe_allow_html=True)
else:
    render_dashboard()