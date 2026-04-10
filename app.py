"""
Digbi Health — Group Coaching Dashboard
Logic: Discovery via Recording API (Bypasses 30-day List limit)
"""

import time
import requests
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date, timezone
from urllib.parse import urlencode, quote

# 1. SETUP
st.set_page_config(page_title="Digbi Deep Sync", page_icon="🧬", layout="wide")

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
    excluded = ["schreiber", "dexcom", "kehe", "ndphit", "silgan", "okaloosa", "azlgebt", "frp", "evry health", "raght", "mohave", "sscgp", "southern", "weston", "prism", "zachry", "city of fw", "city of fort worth", "aaa", "elbit", "vericast", "dexter", "west fargo", "naebt", "cct"]
    if any(k in t for k in excluded): return "Other"

    if "group coaching for members" in t: return COACHING_SERIES[0]
    if "join our group coaching session" in t: return COACHING_SERIES[1]
    if "genetics nutrition" in t: return COACHING_SERIES[2]
    if "gut instincts" in t or "microbiome report" in t: return COACHING_SERIES[3]
    if "glp-1" in t or "wellness benefit" in t or "living well" in t: return COACHING_SERIES[4]
    if "thriving with ibs" in t: return COACHING_SERIES[5]
    if "fine tuning" in t or "fine-tuning" in t: return COACHING_SERIES[6]
    return "Other"

# 3. DATA DISCOVERY ENGINE (The "Logic" Fix)
@st.cache_data(ttl=1800, show_spinner=False)
def discover_sessions_via_recordings(start_date, end_date, token):
    """
    Logic: Standard 'List' APIs are limited. 
    The Recording API allows deep historical date-range searches.
    """
    headers = {"Authorization": f"Bearer {token}"}
    sessions = []
    curr = start_date
    
    while curr < end_date:
        nxt = min(curr + timedelta(days=30), end_date)
        # We use the Recording endpoint because it obeys 'from' and 'to' back to Jan 1st!
        params = {"from": curr.strftime("%Y-%m-%d"), "to": nxt.strftime("%Y-%m-%d"), "page_size": 300}
        r = requests.get(f"{ZOOM_API_BASE}/users/me/recordings", headers=headers, params=params)
        
        if r.status_code == 200:
            # Each recording entry represents a meeting that happened
            sessions.extend(r.json().get("meetings", []))
        curr = nxt + timedelta(days=1)
        
    return sessions

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_participants(uuid, topic, token):
    headers = {"Authorization": f"Bearer {token}"}
    # We try both endpoints because Zoom is inconsistent with types
    for endpoint in ["past_webinars", "past_meetings"]:
        r = requests.get(f"{ZOOM_API_BASE}/{endpoint}/{quote(quote(uuid, safe=''), safe='')}/participants", headers=headers)
        if r.status_code == 200:
            return r.json().get("participants", [])
    return []

# 4. DASHBOARD
def render_dashboard():
    st.sidebar.title("Data Discovery")
    sd = st.sidebar.date_input("Discovery Start", value=date(2026, 1, 1))
    ed = st.sidebar.date_input("Discovery End", value=date.today())
    
    token = st.session_state["token_data"]["access_token"]
    
    with st.spinner("Logic Engine: Searching recording database for Jan-April sessions..."):
        discovered = discover_sessions_via_recordings(sd, ed, token)

    if not discovered:
        st.error("Discovery failed. Ensure Cloud Recording is enabled on the hello@ account.")
        return

    all_participants = []
    mapped_sessions = []

    for item in discovered:
        m_name = map_to_series(item.get("topic", ""))
        if m_name == "Other": continue
        
        item["series_mapped"] = m_name
        mapped_sessions.append(item)
        
        # Get participants using the UUID found in the recording
        pts = fetch_participants(item["uuid"], item["topic"], token)
        for p in pts:
            p.update({"series": m_name, "webinar_id": item["id"]})
            all_participants.append(p)
        time.sleep(0.1)

    df_wb = pd.DataFrame(mapped_sessions)
    df_part = pd.DataFrame(all_participants) if all_participants else pd.DataFrame(columns=["series", "user_email"])

    st.title("Digbi Health - Group Coaching Analytics")
    
    # Discovery Metrics
    m1, m2 = st.columns(2)
    m1.metric("Sessions Discovered (Jan-Apr)", len(df_wb))
    m2.metric("Total Members Synced", df_part["user_email"].nunique() if not df_part.empty else 0)

    # Main Table
    st.subheader("Series Breakdown")
    base = pd.DataFrame({"series": COACHING_SERIES})
    counts = df_wb.groupby("series_mapped").size().reset_index(name="Sessions")
    
    if not df_part.empty:
        stats = df_part.groupby("series").agg(Attendees=("user_email", "count"), Unique=("user_email", "nunique")).reset_index()
    else:
        stats = pd.DataFrame(columns=["series", "Attendees", "Unique"])

    merged = pd.merge(base, counts, left_on="series", right_on="series_mapped", how="left").fillna(0)
    merged = pd.merge(merged, stats, on="series", how="left").fillna(0)
    
    st.dataframe(merged[["series", "Sessions", "Attendees", "Unique"]], use_container_width=True, hide_index=True)

    with st.expander("Show Discovered Sessions List"):
        st.dataframe(df_wb[["start_time", "topic", "uuid"]])

# 5. ENTRY
if "token_data" not in st.session_state:
    if "code" in st.query_params:
        st.session_state["token_data"] = exchange_code(st.query_params["code"])
        st.rerun()
    st.title("Login to Digbi Analytics")
    st.markdown(f'<a href="{get_auth_url()}" target="_self" style="background:#FF4B4B;color:white;padding:12px 24px;text-decoration:none;border-radius:6px;font-weight:bold;display:inline-block;">Connect Zoom Account</a>', unsafe_allow_html=True)
else:
    render_dashboard()