"""
Digbi Health — Group Coaching Dashboard
Admin Power Version: Select Host Account
"""

import time
import requests
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
from urllib.parse import urlencode, quote

# 1. SETUP
st.set_page_config(page_title="Digbi Admin Dashboard", page_icon="🧬", layout="wide")

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
    if uuid_str.startswith('/') or '//' in uuid_str:
        return quote(quote(uuid_str, safe=''), safe='')
    return uuid_str

def map_to_series(topic_str):
    if not isinstance(topic_str, str): return "Other"
    t = topic_str.strip().lower()
    excluded = ["schreiber", "dexcom", "kehe", "ndphit", "silgan", "okaloosa", "azlgebt", "frp", "evry health", "raght", "mohave", "sscgp", "southern", "weston", "prism", "zachry", "city of fw", "city of fort worth", "aaa", "elbit", "vericast", "dexter", "west fargo", "naebt", "cct"]
    if any(k in t for k in excluded): return "Other"
    if "group coaching for members" in t: return COACHING_SERIES[0]
    if "join our group coaching session" in t: return COACHING_SERIES[1]
    if "genetics nutrition" in t: return COACHING_SERIES[2]
    if "gut instincts" in t or "microbiome report" in t: return COACHING_SERIES[3]
    if "glp-1" in t or "wellness benefit" in t or "living well with glp" in t: return COACHING_SERIES[4]
    if "thriving with ibs" in t: return COACHING_SERIES[5]
    if "fine tuning" in t or "fine-tuning" in t: return COACHING_SERIES[6]
    return "Other"

# 3. ADMIN DATA FETCHING
@st.cache_data(ttl=600, show_spinner=False)
def fetch_users_list(token):
    """Fetches all users in the Zoom account (Admin scope required)."""
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{ZOOM_API_BASE}/users", headers=headers, params={"page_size": 300})
    if r.status_code == 200:
        return [u['email'] for u in r.json().get('users', [])]
    return []

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_sessions_for_user(target_email, start_date, end_date, token):
    results = []
    headers = {"Authorization": f"Bearer {token}"}
    # Fetch Webinars
    p_w = {"type": "past", "from": start_date.strftime("%Y-%m-%d"), "to": end_date.strftime("%Y-%m-%d"), "page_size": 300}
    r_w = requests.get(f"{ZOOM_API_BASE}/users/{target_email}/webinars", headers=headers, params=p_w)
    if r_w.status_code == 200: results.extend(r_w.json().get("webinars", []))
    # Fetch Meetings
    r_m = requests.get(f"{ZOOM_API_BASE}/users/{target_email}/meetings", headers=headers, params=p_w)
    if r_m.status_code == 200: results.extend(r_m.json().get("meetings", []))
    return results

# 4. DASHBOARD UI
def render_dashboard():
    token = st.session_state["token_data"]["access_token"]
    
    # Identify currently logged in user
    headers = {"Authorization": f"Bearer {token}"}
    me = requests.get(f"{ZOOM_API_BASE}/users/me", headers=headers).json()
    my_email = me.get('email', 'Unknown')

    st.sidebar.title("Admin Controls")
    st.sidebar.write(f"Logged in as: **{my_email}**")
    
    # Get all users and let admin pick the host
    with st.spinner("Loading account users..."):
        all_users = fetch_users_list(token)
    
    if not all_users:
        all_users = [my_email] # Fallback if not admin
    
    # Try to default to hello@ if it exists in the list
    default_idx = all_users.index("hello@digbihealth.com") if "hello@digbihealth.com" in all_users else 0
    target_user = st.sidebar.selectbox("Select Webinar Host", options=all_users, index=default_idx)

    st.sidebar.markdown("---")
    sd = st.sidebar.date_input("Start Date", value=date(2026, 1, 1))
    ed = st.sidebar.date_input("End Date", value=date.today())

    if st.sidebar.button("Logout"):
        st.session_state.clear()
        st.rerun()

    st.title(f"Digbi Coaching Dashboard: {target_user}")

    with st.spinner(f"Fetching data for {target_user}..."):
        sessions = fetch_sessions_for_user(target_user, sd, ed, token)

    if not sessions:
        st.warning(f"No sessions found for {target_user}. Is this the correct host?")
        return

    df_wb = pd.DataFrame(sessions)
    df_wb["series_mapped"] = df_wb["topic"].apply(map_to_series)

    # Filtered Table
    base = pd.DataFrame({"series": COACHING_SERIES})
    counts = df_wb[df_wb["series_mapped"] != "Other"].groupby("series_mapped").size().reset_index(name="Sessions")
    merged = pd.merge(base, counts, left_on="series", right_on="series_mapped", how="left").fillna(0)
    
    st.subheader("Series Performance Breakdown")
    st.dataframe(merged[["series", "Sessions"]], use_container_width=True, hide_index=True)

    with st.expander("Debug: All topics found for this host"):
        st.dataframe(df_wb[["start_time", "topic", "series_mapped"]].sort_values("start_time", ascending=False))

# 5. ENTRY
if "token_data" not in st.session_state:
    if "code" in st.query_params:
        st.session_state["token_data"] = exchange_code(st.query_params["code"])
        st.rerun()
    st.title("Connect Digbi Zoom Account")
    st.markdown(f'<a href="{get_auth_url()}" target="_self" style="background:#FF4B4B;color:white;padding:12px 24px;text-decoration:none;border-radius:6px;font-weight:bold;display:inline-block;">Login to Zoom</a>', unsafe_allow_html=True)
else:
    render_dashboard()