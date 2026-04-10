"""
Digbi Health — Group Coaching Dashboard
Version: Instance Reconstruction Engine (Bypasses Report API)
"""

import time
import requests
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date, timezone
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

def safe_encode_uuid(uuid_str):
    """Crucial: Zoom requires double-encoding if a UUID contains a slash."""
    uuid_str = str(uuid_str)
    if '/' in uuid_str or '//' in uuid_str:
        return quote(quote(uuid_str, safe=''), safe='')
    return uuid_str

def map_to_series(topic_str):
    if not isinstance(topic_str, str): return "Other"
    t = topic_str.strip().lower()
    
    # Exclusion List
    excluded = ["schreiber", "dexcom", "kehe", "ndphit", "silgan", "okaloosa", "azlgebt", "frp", "evry health", "raght", "mohave", "sscgp", "southern", "weston", "prism", "zachry", "city of fw", "city of fort worth", "aaa", "elbit", "vericast", "dexter", "west fargo", "naebt", "cct"]
    if any(k in t for k in excluded): return "Other"

    # Core Mapping based exactly on your CSVs
    if "group coaching for members" in t: return COACHING_SERIES[0]
    if "join our group coaching session" in t: return COACHING_SERIES[1]
    if "genetics nutrition" in t: return COACHING_SERIES[2]
    if "gut instincts" in t or "microbiome report" in t: return COACHING_SERIES[3]
    if "glp-1" in t or "wellness benefit" in t or "living well" in t: return COACHING_SERIES[4]
    if "thriving with ibs" in t: return COACHING_SERIES[5]
    if "fine tuning" in t or "fine-tuning" in t: return COACHING_SERIES[6]
    return "Other"

# 3. RECONSTRUCTION ENGINE (Uses only the scopes you have!)
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_parent_series(token):
    """Gets all active recurring parents."""
    headers = {"Authorization": f"Bearer {token}"}
    parents = []
    
    for endpoint in ["webinars", "meetings"]:
        r = requests.get(f"{ZOOM_API_BASE}/users/me/{endpoint}", headers=headers, params={"page_size": 300})
        if r.status_code == 200:
            for item in r.json().get(endpoint, []):
                item["is_webinar"] = (endpoint == "webinars")
                parents.append(item)
    return parents

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_historical_instances(parent_id, is_webinar, token):
    """Drills down to find the historical dates the parent actually occurred."""
    headers = {"Authorization": f"Bearer {token}"}
    endpoint = f"past_webinars/{parent_id}/instances" if is_webinar else f"past_meetings/{parent_id}/instances"
    r = requests.get(f"{ZOOM_API_BASE}/{endpoint}", headers=headers)
    if r.status_code == 200:
        key = "webinars" if is_webinar else "meetings"
        return r.json().get(key, [])
    return []

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_participants_cached(uuid, is_webinar, token):
    """Gets the participants for the specific historical instance."""
    headers = {"Authorization": f"Bearer {token}"}
    safe_id = safe_encode_uuid(uuid)
    endpoint = f"past_webinars/{safe_id}/participants" if is_webinar else f"past_meetings/{safe_id}/participants"
    r = requests.get(f"{ZOOM_API_BASE}/{endpoint}", headers=headers, params={"page_size": 300})
    return r.json().get("participants", []) if r.status_code == 200 else []

# 4. DASHBOARD
def render_dashboard():
    st.sidebar.title("Sync Filters")
    sd = st.sidebar.date_input("Start Date", value=date(2026, 1, 1))
    ed = st.sidebar.date_input("End Date", value=date.today())
    
    token = st.session_state["token_data"]["access_token"]
    
    with st.spinner("Reconstructing session history using your authorized scopes..."):
        parents = fetch_parent_series(token)

    if not parents:
        st.error("No recurring series found. Ensure you are logged in as hello@digbihealth.com.")
        return

    all_participants = []
    mapped_data = []

    for parent in parents:
        m_series = map_to_series(parent.get("topic", ""))
        
        # We only care about drilling down into Core Coaching sessions
        if m_series == "Other": continue

        # Fetch the past instances of this series
        instances = fetch_historical_instances(parent["id"], parent["is_webinar"], token)
        
        for inst in instances:
            if "start_time" not in inst: continue
            
            inst_dt = datetime.fromisoformat(inst["start_time"].replace("Z", "+00:00")).date()
            
            # Check if this historical occurrence falls in your sidebar date range
            if sd <= inst_dt <= ed:
                session_info = {
                    "topic": parent["topic"],
                    "series_mapped": m_series,
                    "session_date": inst_dt,
                    "id": parent["id"],
                    "uuid": inst["uuid"],
                }
                mapped_data.append(session_info)
                
                # Get attendees for this specific occurrence
                pts = fetch_participants_cached(inst["uuid"], parent["is_webinar"], token)
                for p in pts:
                    p.update({"series": m_series, "session_date": inst_dt})
                    all_participants.append(p)
                time.sleep(0.05)

    df_wb = pd.DataFrame(mapped_data)
    df_part = pd.DataFrame(all_participants) if all_participants else pd.DataFrame(columns=["series", "user_email"])

    st.title("Digbi Health - Group Coaching Analytics")
    
    if df_wb.empty:
        st.warning(f"Found recurring series, but no historical occurrences found between {sd} and {ed}.")
        return

    # ── KPIs ──
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Core Sessions", len(df_wb))
    c2.metric("Total Attendees", len(df_part))
    c3.metric("Unique Members", df_part["user_email"].nunique() if not df_part.empty else 0)

    # ── SUMMARY TABLE ──
    st.subheader("Performance Breakdown")
    base = pd.DataFrame({"series": COACHING_SERIES})
    counts = df_wb.groupby("series_mapped").size().reset_index(name="Sessions")
    
    if not df_part.empty:
        stats = df_part.groupby("series").agg(Attendees=("user_email", "count"), Unique=("user_email", "nunique")).reset_index()
    else:
        stats = pd.DataFrame(columns=["series", "Attendees", "Unique"])

    merged = pd.merge(base, counts, left_on="series", right_on="series_mapped", how="left").fillna(0)
    merged = pd.merge(merged, stats, on="series", how="left").fillna(0)
    merged["Avg Attendance"] = (merged["Attendees"] / merged["Sessions"]).fillna(0).round(1)
    
    st.dataframe(merged[["series", "Sessions", "Attendees", "Unique", "Avg Attendance"]].sort_values("Sessions", ascending=False), use_container_width=True, hide_index=True)

# 5. ENTRY
if "token_data" not in st.session_state:
    if "code" in st.query_params:
        st.session_state["token_data"] = exchange_code(st.query_params["code"])
        st.rerun()
    st.title("Digbi Analytics Login")
    login_url = get_auth_url()
    st.markdown(f'<a href="{login_url}" target="_self" style="background:#FF4B4B;color:white;padding:12px 24px;text-decoration:none;border-radius:6px;font-weight:bold;display:inline-block;">Login to Zoom</a>', unsafe_allow_html=True)
else:
    render_dashboard()