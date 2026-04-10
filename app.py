"""
Digbi Health — Group Coaching Dashboard
Version: The Hybrid Engine (Zoom API + CSV History)
"""

import time
import requests
import streamlit as st
import pandas as pd
from datetime import datetime, date
from urllib.parse import urlencode, quote

# 1. SETUP
st.set_page_config(page_title="Digbi Hybrid Analytics", page_icon="🧬", layout="wide")

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

def safe_encode_uuid(uuid_str):
    uuid_str = str(uuid_str)
    if '/' in uuid_str or '//' in uuid_str:
        return quote(quote(uuid_str, safe=''), safe='')
    return quote(uuid_str)

def map_to_series(topic_str):
    if not isinstance(topic_str, str): return "Other"
    t = topic_str.strip().lower()
    
    excluded = ["schreiber", "dexcom", "kehe", "ndphit", "silgan", "okaloosa", "azlgebt", "frp", "evry health", "raght", "mohave", "sscgp", "southern", "weston", "prism", "zachry", "city of fw", "city of fort worth", "aaa", "elbit", "vericast", "dexter", "west fargo", "naebt", "cct", "southern star"]
    if any(k in t for k in excluded): return "Other"

    if "group coaching for members" in t: return COACHING_SERIES[0]
    if "join our group coaching session" in t: return COACHING_SERIES[1]
    if "genetics" in t or "nutrition" in t: return COACHING_SERIES[2]
    if "instincts" in t or "microbiome" in t: return COACHING_SERIES[3]
    if "glp" in t or "wellness benefit" in t or "living well" in t: return COACHING_SERIES[4]
    if "ibs" in t or "irritable" in t: return COACHING_SERIES[5]
    if "fine-tuning" in t or "fine tuning" in t: return COACHING_SERIES[6]
    return "Other"

# 3. CSV PARSER (Historical Data)
def parse_csv_history(uploaded_files):
    sessions_list = []
    parts_list = []
    
    for file in uploaded_files:
        df = pd.read_csv(file)
        if 'Topic' not in df.columns or 'Start time' not in df.columns:
            continue
            
        for _, row in df.iterrows():
            mapped = map_to_series(row['Topic'])
            if mapped == "Other": continue
            
            m_id = str(row['ID']).replace(" ", "")
            
            sessions_list.append({
                "topic": row['Topic'],
                "series_mapped": mapped,
                "id": m_id,
                "start_time": row['Start time'],
                "source": "CSV History"
            })
            
            # If it's a participant CSV with emails
            if 'Email' in df.columns and pd.notna(row['Email']):
                parts_list.append({
                    "webinar_id": m_id,
                    "user_email": row['Email'].strip().lower(),
                    "series": mapped
                })
                
    df_s = pd.DataFrame(sessions_list).drop_duplicates(subset=['id', 'start_time']) if sessions_list else pd.DataFrame()
    df_p = pd.DataFrame(parts_list).drop_duplicates(subset=['webinar_id', 'user_email']) if parts_list else pd.DataFrame()
    return df_s, df_p

# 4. ZOOM API ENGINE (Last 30 Days Live Sync)
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_recent_api(token):
    headers = {"Authorization": f"Bearer {token}"}
    sessions = []
    
    for endpoint in ["webinars", "meetings"]:
        r = requests.get(f"{ZOOM_API_BASE}/users/me/{endpoint}", headers=headers, params={"type": "past", "page_size": 300})
        if r.status_code == 200:
            for item in r.json().get(endpoint, []):
                item["is_webinar"] = (endpoint == "webinars")
                sessions.append(item)
    return sessions

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_api_participants(uuid, is_webinar, token):
    headers = {"Authorization": f"Bearer {token}"}
    safe_id = safe_encode_uuid(uuid)
    endpoint = f"past_webinars/{safe_id}/participants" if is_webinar else f"past_meetings/{safe_id}/participants"
    r = requests.get(f"{ZOOM_API_BASE}/{endpoint}", headers=headers, params={"page_size": 300})
    return r.json().get("participants", []) if r.status_code == 200 else []

# 5. DASHBOARD UI
def render_dashboard():
    st.sidebar.title("Data Sources")
    
    # Drag and Drop for your CSV files!
    uploaded_files = st.sidebar.file_uploader("Upload Historical Zoom CSVs", type=['csv'], accept_multiple_files=True)
    
    st.sidebar.markdown("---")
    token = st.session_state["token_data"]["access_token"]
    
    # 1. Parse uploaded CSVs
    df_csv_sessions, df_csv_parts = parse_csv_history(uploaded_files)
    
    # 2. Fetch Recent API Data
    with st.spinner("Fetching Live API Data (Last 30 Days)..."):
        api_raw = fetch_recent_api(token)
        
    api_sessions = []
    api_parts = []
    
    for item in api_raw:
        m_series = map_to_series(item.get("topic", ""))
        if m_series == "Other": continue
        
        item["series_mapped"] = m_series
        item["source"] = "Live API"
        api_sessions.append(item)
        
        pts = fetch_api_participants(item["uuid"], item.get("is_webinar", True), token)
        for p in pts:
            api_parts.append({
                "webinar_id": str(item["id"]),
                "user_email": p.get("user_email", "").strip().lower(),
                "series": m_series
            })
            
    df_api_sessions = pd.DataFrame(api_sessions)
    df_api_parts = pd.DataFrame(api_parts)

    # 3. MERGE HYBRID DATA
    st.title("Digbi Health - Hybrid Analytics Dashboard")
    
    final_sessions = pd.concat([df_csv_sessions, df_api_sessions], ignore_index=True)
    if not final_sessions.empty:
        # Drop duplicates in case a session is in BOTH the CSV and the recent API fetch
        final_sessions = final_sessions.drop_duplicates(subset=['id', 'start_time'], keep='first')
        
    final_parts = pd.concat([df_csv_parts, df_api_parts], ignore_index=True)
    if not final_parts.empty:
        final_parts = final_parts[final_parts['user_email'] != ""]
        final_parts = final_parts.drop_duplicates(subset=['webinar_id', 'user_email'])

    if final_sessions.empty:
        st.warning("No data found. Please upload your Zoom CSVs in the sidebar to view historical data.")
        return

    # ── KPIs ──
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Core Sessions", len(final_sessions))
    c2.metric("Total Attendees", len(final_parts))
    c3.metric("Unique Members", final_parts["user_email"].nunique() if not final_parts.empty else 0)

    # ── SUMMARY TABLE ──
    st.subheader("Series Performance Breakdown")
    base = pd.DataFrame({"series": COACHING_SERIES})
    counts = final_sessions.groupby("series_mapped").size().reset_index(name="Sessions")
    
    if not final_parts.empty:
        stats = final_parts.groupby("series").agg(Attendees=("user_email", "count"), Unique=("user_email", "nunique")).reset_index()
    else:
        stats = pd.DataFrame(columns=["series", "Attendees", "Unique"])

    merged = pd.merge(base, counts, left_on="series", right_on="series_mapped", how="left").fillna(0)
    merged = pd.merge(merged, stats, on="series", how="left").fillna(0)
    merged["Avg Attendance"] = (merged["Attendees"] / merged["Sessions"]).fillna(0).round(1)
    
    st.dataframe(merged[["series", "Sessions", "Attendees", "Unique", "Avg Attendance"]].sort_values("Sessions", ascending=False), use_container_width=True, hide_index=True)

    with st.expander("View Underlying Data Map (See where data came from)"):
        st.dataframe(final_sessions[["start_time", "topic", "series_mapped", "source"]].sort_values("start_time", ascending=False))

# 6. ENTRY
if "token_data" not in st.session_state:
    if "code" in st.query_params:
        st.session_state["token_data"] = exchange_code(st.query_params["code"])
        st.rerun()
    st.title("Digbi Analytics Login")
    st.markdown(f'<a href="{get_auth_url()}" target="_self" style="background:#FF4B4B;color:white;padding:12px 24px;text-decoration:none;border-radius:6px;font-weight:bold;display:inline-block;">Login to Zoom</a>', unsafe_allow_html=True)
else:
    render_dashboard()