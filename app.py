"""
Digbi Health — Group Coaching Dashboard
Zoom Reports API · Streamlit Cloud
"""

import time
import requests
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from urllib.parse import urlencode, quote

# 1. DEFINITIONS AND CONFIGURATION (Must be at the very top)
st.set_page_config(page_title="Digbi Group Coaching", page_icon="🧬", layout="wide")

CLIENT_ID     = st.secrets["ZOOM_CLIENT_ID"]
CLIENT_SECRET = st.secrets["ZOOM_CLIENT_SECRET"]
REDIRECT_URI  = st.secrets["ZOOM_REDIRECT_URI"]
ZOOM_API_BASE = "https://api.zoom.us/v2"

# Exact character-matched titles from your CSV reports
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
    """Generates the Zoom OAuth login URL."""
    payload = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI
    }
    return f"https://zoom.us/oauth/authorize?{urlencode(payload)}"

def exchange_code(auth_code):
    """Exchanges the temporary code for a permanent access token."""
    response = requests.post(
        "https://zoom.us/oauth/token",
        params={
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": REDIRECT_URI
        },
        auth=(CLIENT_ID, CLIENT_SECRET)
    )
    return response.json()

def safe_encode_uuid(uuid_str):
    """Encodes Zoom UUIDs. Crucial if they start with a slash."""
    if uuid_str.startswith('/') or '//' in uuid_str:
        return quote(quote(uuid_str, safe=''), safe='')
    return uuid_str

def map_to_series(topic_str):
    """Filters client-specific webinars and maps others to the core 7 series."""
    if not isinstance(topic_str, str): return "Other"
    
    t = topic_str.strip().lower()
    
    # Exclusion list for one-off client webinars
    excluded = ["schreiber", "dexcom", "kehe", "ndphit", "silgan", "okaloosa", "azlgebt", "frp", "evry health", "raght", "mohave", "sscgp", "southern", "weston", "prism", "zachry", "city of fw", "city of fort worth", "aaa", "elbit", "vericast", "dexter", "west fargo", "naebt", "cct"]
    if any(keyword in t for keyword in excluded): return "Other"

    # Exact Title Matching
    if "group coaching for members" in t: return COACHING_SERIES[0]
    if "join our group coaching session" in t: return COACHING_SERIES[1]
    if "genetics nutrition" in t: return COACHING_SERIES[2]
    if "gut instincts" in t or "microbiome report" in t: return COACHING_SERIES[3]
    if "glp-1" in t or "wellness benefit" in t: return COACHING_SERIES[4]
    if "thriving with ibs" in t: return COACHING_SERIES[5]
    if "fine tuning" in t or "fine-tuning" in t: return COACHING_SERIES[6]
    
    return "Other"

# 3. DATA FETCHING (Report API)

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_webinar_history(from_dt, to_dt, token):
    """Fetches every session instance from Zoom Reports."""
    results = []
    headers = {"Authorization": f"Bearer {token}"}
    
    current = from_dt
    while current < to_dt:
        nxt = min(current + timedelta(days=30), to_dt)
        params = {"from": current.strftime("%Y-%m-%d"), "to": nxt.strftime("%Y-%m-%d"), "page_size": 300}
        resp = requests.get(f"{ZOOM_API_BASE}/report/users/me/webinars", headers=headers, params=params)
        if resp.status_code == 200:
            results.extend(resp.json().get("webinars", []))
        current = nxt + timedelta(days=1)
    return results

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_attendees(uuid_val, token):
    """Fetches the participant list for a specific instance."""
    headers = {"Authorization": f"Bearer {token}"}
    safe_id = safe_encode_uuid(uuid_val)
    resp = requests.get(f"{ZOOM_API_BASE}/report/webinars/{safe_id}/participants", headers=headers, params={"page_size": 300})
    return resp.json().get("participants", []) if resp.status_code == 200 else []

# 4. DASHBOARD PAGE

def render_dashboard():
    st.sidebar.header("Date Filters")
    start_date = st.sidebar.date_input("Start Date", value=date(2026, 1, 1))
    end_date = st.sidebar.date_input("End Date", value=date.today())

    access_token = st.session_state["token_data"]["access_token"]

    with st.spinner("Syncing 2026 data from Zoom Reports..."):
        instances = fetch_webinar_history(start_date, end_date, access_token)

    if not instances:
        st.info("No sessions found in this date range.")
        return

    all_parts = []
    found_sessions = []

    for item in instances:
        mapped_name = map_to_series(item.get("topic", ""))
        if mapped_name == "Other": continue
        
        item["series"] = mapped_name
        found_sessions.append(item)
        
        # Fetch actual attendees for this session
        parts = fetch_attendees(item["uuid"], access_token)
        for p in parts:
            p.update({"series": mapped_name, "webinar_id": item["id"]})
            all_parts.append(p)
        time.sleep(0.1)

    df_wb = pd.DataFrame(found_sessions)
    df_part = pd.DataFrame(all_parts)

    st.title("Digbi Health - Group Coaching Dashboard")
    
    # Metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Sessions", len(df_wb))
    c2.metric("Total Attendees", len(df_part))
    c3.metric("Unique Members", df_part["user_email"].nunique() if not df_part.empty else 0)
    c4.metric("Avg Attendance", round(len(df_part)/len(df_wb), 1) if len(df_wb)>0 else 0)

    # Breakdown Table
    st.subheader("Stats for 7 Core Coaching Series")
    base = pd.DataFrame({"series": COACHING_SERIES})
    counts = df_wb.groupby("series").size().reset_index(name="Sessions")
    
    if not df_part.empty:
        stats = df_part.groupby("series").agg(
            Total_Attendees=("user_email", "count"),
            Unique_Members=("user_email", "nunique")
        ).reset_index()
    else:
        stats = pd.DataFrame(columns=["series", "Total_Attendees", "Unique_Members"])

    merged = pd.merge(base, counts, on="series", how="left").fillna(0)
    merged = pd.merge(merged, stats, on="series", how="left").fillna(0)
    merged["Avg Sessions / Attendee"] = merged.apply(
        lambda r: round(r["Total_Attendees"]/r["Unique_Members"], 2) if r["Unique_Members"] > 0 else 0, axis=1
    )

    st.dataframe(
        merged.rename(columns={"series": "Coaching Series"}).sort_values("Total_Attendees", ascending=False), 
        use_container_width=True, 
        hide_index=True
    )

# 5. MAIN LOGIC (Application Entry Point)

if "token_data" not in st.session_state:
    # Check if we are returning from Zoom login
    if "code" in st.query_params:
        st.session_state["token_data"] = exchange_code(st.query_params["code"])
        st.rerun()
    
    # Connection Screen
    st.title("Digbi Group Coaching Dashboard")
    st.write("Please log in with the Zoom account that hosts the webinars.")
    
    # We define the URL here, right before using it
    zoom_url = get_auth_url()
    st.markdown(
        f'<a href="{zoom_url}" target="_self" style="background:#FF4B4B;color:white;padding:12px 24px;text-decoration:none;border-radius:6px;font-weight:bold;display:inline-block;">Connect Zoom Account</a>', 
        unsafe_allow_html=True
    )
else:
    # If already logged in, show the data
    render_dashboard()