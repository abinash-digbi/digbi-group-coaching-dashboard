import time
import requests
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
from urllib.parse import urlencode, quote

# 1. SETUP
st.set_page_config(page_title="Digbi Group Coaching Dashboard", page_icon="🧬", layout="wide")

CLIENT_ID     = st.secrets["ZOOM_CLIENT_ID"]
CLIENT_SECRET = st.secrets["ZOOM_CLIENT_SECRET"]
REDIRECT_URI  = st.secrets["ZOOM_REDIRECT_URI"]
ZOOM_API_BASE = "https://api.zoom.us/v2"

# Host email identified from your Jan-Apr CSV reports
TARGET_HOST_EMAIL = "hello@digbihealth.com" 

# Exact session titles character-matched from your CSV files
COACHING_SERIES = [
    "Digbi Health Orientation & How to Eat Smart - Group Coaching for Members",
    "Digbi Health Orientation & How to Eat Smart - Join Our Group Coaching Session",
    "Learn to Read and Apply Your Genetics Nutrition and Gut Monitoring Reports for Better Health",
    "Follow Your Gut Instincts: Understanding Your Gut Microbiome Report",
    "Introducing Digbi Health: An Exclusive Wellness Benefit with access to GLP-1s",
    "Thriving with IBS: A Group Coaching Program for Relief and Empowerment",
    "Fine-Tuning Your Routine: Advanced Tips for Continued Weight Loss"
]

# 2. CORE LOGIC FUNCTIONS
def get_auth_url():
    params = {"response_type": "code", "client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI}
    return f"https://zoom.us/oauth/authorize?{urlencode(params)}"

def exchange_code(auth_code):
    r = requests.post("https://zoom.us/oauth/token", params={"grant_type": "authorization_code", "code": auth_code, "redirect_uri": REDIRECT_URI}, auth=(CLIENT_ID, CLIENT_SECRET))
    return r.json()

def safe_encode_uuid(uuid_str):
    """Encodes UUIDs to handle slashes correctly for Zoom API."""
    if uuid_str.startswith('/') or '//' in uuid_str:
        return quote(quote(uuid_str, safe=''), safe='')
    return uuid_str

def map_to_series(topic_str):
    """Maps Zoom topics to core coaching series and filters company-specific sessions."""
    if not isinstance(topic_str, str): return "Other"
    t = topic_str.strip().lower()
    
    # Exclusion List: Block one-off client webinars
    excluded = ["schreiber", "dexcom", "kehe", "ndphit", "silgan", "okaloosa", "azlgebt", "frp", "evry health", "raght", "mohave", "sscgp", "southern", "weston", "prism", "zachry", "city of fw", "city of fort worth", "aaa", "elbit", "vericast", "dexter", "west fargo", "naebt", "cct"]
    if any(k in t for k in excluded): return "Other"

    # Precise matching based on your CSV history
    if "group coaching for members" in t: return COACHING_SERIES[0]
    if "join our group coaching session" in t: return COACHING_SERIES[1]
    if "genetics nutrition" in t: return COACHING_SERIES[2]
    if "gut instincts" in t or "microbiome report" in t: return COACHING_SERIES[3]
    if "glp-1" in t or "wellness benefit" in t: return COACHING_SERIES[4]
    if "thriving with ibs" in t: return COACHING_SERIES[5]
    if "fine tuning" in t or "fine-tuning" in t: return COACHING_SERIES[6]
    return "Other"

# 3. DATA FETCHING (Reports API for Historical Accuracy)
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_full_history(start_date, end_date, token):
    all_webinars = []
    headers = {"Authorization": f"Bearer {token}"}
    curr = start_date
    while curr < end_date:
        nxt = min(curr + timedelta(days=30), end_date)
        params = {"from": curr.strftime("%Y-%m-%d"), "to": nxt.strftime("%Y-%m-%d"), "page_size": 300}
        resp = requests.get(f"{ZOOM_API_BASE}/report/users/{TARGET_HOST_EMAIL}/webinars", headers=headers, params=params)
        if resp.status_code == 200:
            all_webinars.extend(resp.json().get("webinars", []))
        elif resp.status_code == 403:
            st.sidebar.error("Permission Denied: Your account cannot view reports for hello@digbihealth.com")
            return []
        curr = nxt + timedelta(days=1)
    return all_webinars

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_participants(uuid_val, token):
    headers = {"Authorization": f"Bearer {token}"}
    safe_id = safe_encode_uuid(uuid_val)
    r = requests.get(f"{ZOOM_API_BASE}/report/webinars/{safe_id}/participants", headers=headers, params={"page_size": 300})
    return r.json().get("participants", []) if r.status_code == 200 else []

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_cloud_recording(webinar_id, token):
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{ZOOM_API_BASE}/webinars/{webinar_id}/recordings", headers=headers)
    return r.json().get("share_url", "") if r.status_code == 200 else "N/A"

# 4. DASHBOARD UI
def render_dashboard():
    st.sidebar.header("Filter Sync")
    sd = st.sidebar.date_input("From", value=date(2026, 1, 1))
    ed = st.sidebar.date_input("To", value=date.today())

    token = st.session_state["token_data"]["access_token"]
    
    with st.spinner(f"Syncing all sessions for {TARGET_HOST_EMAIL}..."):
        instances = fetch_full_history(sd, ed, token)

    if not instances:
        st.warning(f"No sessions found. Ensure you are an Admin of the {TARGET_HOST_EMAIL} account.")
        return

    all_parts = []
    mapped_list = []

    for item in instances:
        m_name = map_to_series(item.get("topic", ""))
        if m_name == "Other": continue
        
        item["series"] = m_name
        item["recording"] = fetch_cloud_recording(item["id"], token)
        mapped_list.append(item)
        
        # Fetch Attendees
        pts = fetch_participants(item["uuid"], token)
        for p in pts:
            p.update({"series": m_name, "webinar_id": item["id"]})
            all_parts.append(p)
        time.sleep(0.1)

    df_wb = pd.DataFrame(mapped_list)
    df_part = pd.DataFrame(all_parts)

    st.title("Digbi Health - Group Coaching Dashboard")
    
    # ── KPIs ──
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Sessions", len(df_wb))
    c2.metric("Total Attendees", len(df_part))
    c3.metric("Unique Members", df_part["user_email"].nunique() if not df_part.empty else 0)
    c4.metric("Avg Attendance", round(len(df_part)/len(df_wb), 1) if len(df_wb)>0 else 0)

    # ── STATS TABLE ──
    st.subheader("Series Performance & Recording Status")
    base = pd.DataFrame({"series": COACHING_SERIES})
    counts = df_wb.groupby("series").agg(Sessions=("id", "size"), Recorded=("recording", lambda x: (x != "N/A").sum())).reset_index()
    
    if not df_part.empty:
        stats = df_part.groupby("series").agg(Attendees=("user_email", "count"), Unique=("user_email", "nunique")).reset_index()
    else:
        stats = pd.DataFrame(columns=["series", "Attendees", "Unique"])

    merged = pd.merge(base, counts, on="series", how="left").fillna(0)
    merged = pd.merge(merged, stats, on="series", how="left").fillna(0)
    
    st.dataframe(merged.sort_values("Attendees", ascending=False), use_container_width=True, hide_index=True)

    # ── RECORDING TRACKER ──
    st.markdown("---")
    st.subheader("🎥 Latest Cloud Recording Links")
    st.write("For Varun and Vibhav to share post-session.")
    if not df_wb.empty:
        st.dataframe(df_wb[["start_time", "series", "recording"]].sort_values("start_time", ascending=False).head(10), use_container_width=True, hide_index=True)

# 5. ENTRY POINT
if "token_data" not in st.session_state:
    if "code" in st.query_params:
        st.session_state["token_data"] = exchange_code(st.query_params["code"])
        st.rerun()
    st.title("Connect to Digbi Coaching Account")
    st.markdown(f'<a href="{get_auth_url()}" target="_self" style="background:#FF4B4B;color:white;padding:12px 24px;text-decoration:none;border-radius:6px;font-weight:bold;display:inline-block;">Login to Zoom</a>', unsafe_allow_html=True)
else:
    render_dashboard()