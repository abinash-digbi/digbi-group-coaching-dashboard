"""
Digbi Health — Group Coaching Dashboard
Zoom Webinars API · Streamlit Cloud
"""

import os
import time
import urllib.parse
import requests
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date, timezone
from zoneinfo import ZoneInfo

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="Digbi Group Coaching", page_icon="🧬", layout="wide")

# ── Zoom credentials ─────────────────────────────────────────────────────────
CLIENT_ID     = st.secrets["ZOOM_CLIENT_ID"]
CLIENT_SECRET = st.secrets["ZOOM_CLIENT_SECRET"]
REDIRECT_URI  = st.secrets["ZOOM_REDIRECT_URI"]
ZOOM_API_BASE = "https://api.zoom.us/v2"

# ── The 7 Core Series (Exact Titles from your CSV Reports) ──────────────────
COACHING_SERIES = [
    "Digbi Health Orientation & How to Eat Smart - Group Coaching for Members",
    "Digbi Health Orientation & How to Eat Smart - Join Our Group Coaching Session",
    "Learn to Read and Apply Your Genetics Nutrition and Gut Monitoring Reports for Better Health",
    "Follow Your Gut Instincts: Understanding Your Gut Microbiome Report",
    "Introducing Digbi Health: An Exclusive Wellness Benefit with access to GLP-1s",
    "Thriving with IBS: A Group Coaching Program for Relief and Empowerment",
    "Fine-Tuning Your Routine: Advanced Tips for Continued Weight Loss"
]

def map_to_series(topic: str) -> str:
    if not isinstance(topic, str): return "Other"
    t = topic.strip().lower()

    # 1. Exclusion List
    raw_excluded = st.secrets.get("EXCLUDED_KEYWORDS", [])
    excluded = [k.strip().lower() for k in (raw_excluded.split(",") if isinstance(raw_excluded, str) else raw_excluded)]
    if any(k in t for k in excluded): return "Other"

    # 2. Exact Title Matching (Aggregating slight variations like GLP-1)
    if "group coaching for members" in t:
        return "Digbi Health Orientation & How to Eat Smart - Group Coaching for Members"
    if "join our group coaching session" in t:
        return "Digbi Health Orientation & How to Eat Smart - Join Our Group Coaching Session"
    if "genetics nutrition" in t:
        return "Learn to Read and Apply Your Genetics Nutrition and Gut Monitoring Reports for Better Health"
    if "gut instincts" in t or "microbiome report" in t:
        return "Follow Your Gut Instincts: Understanding Your Gut Microbiome Report"
    if "glp-1" in t or "exclusive wellness benefit" in t:
        return "Introducing Digbi Health: An Exclusive Wellness Benefit with access to GLP-1s"
    if "thriving with ibs" in t:
        return "Thriving with IBS: A Group Coaching Program for Relief and Empowerment"
    if "fine tuning" in t or "fine-tuning" in t:
        return "Fine-Tuning Your Routine: Advanced Tips for Continued Weight Loss"
    
    return "Other"

def get_headers():
    if "token_data" not in st.session_state: return None
    return {"Authorization": f"Bearer {st.session_state['token_data']['access_token']}"}

def safe_encode_uuid(uuid):
    """Crucial for Zoom: Double encodes UUIDs starting with / or containing //."""
    if uuid.startswith('/') or '//' in uuid:
        return urllib.parse.quote(urllib.parse.quote(uuid, safe=''), safe='')
    return uuid

# ── Robust Data Fetching using Reports API ───────────────────────────────────
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_webinar_report(from_date, to_date, headers):
    """Uses the Report API to get all historical instances."""
    all_instances = []
    # Reports API also has a 1-month window limit
    curr_start = from_date
    while curr_start < to_date:
        curr_end = min(curr_start + timedelta(days=30), to_date)
        params = {"from": curr_start.strftime("%Y-%m-%d"), "to": curr_end.strftime("%Y-%m-%d"), "page_size": 300}
        r = requests.get(f"{ZOOM_API_BASE}/report/users/me/webinars", headers=headers, params=params)
        if r.status_code == 200:
            all_instances.extend(r.json().get("webinars", []))
        curr_start = curr_end + timedelta(days=1)
    return all_instances

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_participants_list(uuid, headers):
    safe_uuid = safe_encode_uuid(uuid)
    r = requests.get(f"{ZOOM_API_BASE}/report/webinars/{safe_uuid}/participants", headers=headers, params={"page_size": 300})
    return r.json().get("participants", []) if r.status_code == 200 else []

def render_dashboard():
    st.sidebar.header("Filter Settings")
    from_date = st.sidebar.date_input("Start Date", value=date(2026, 1, 1))
    to_date = st.sidebar.date_input("End Date", value=date.today())
    
    headers = get_headers()
    with st.spinner("Fetching data using Zoom Reports API..."):
        instances = fetch_webinar_report(from_date, to_date, headers)

    if not instances:
        st.warning("No past webinars found. Check if the logged-in user is the host or has report access.")
        return

    all_participants = []
    mapped_instances = []

    for inst in instances:
        series = map_to_series(inst.get("topic", ""))
        if series == "Other": continue
        
        # Prepare instance data
        inst_date = inst["start_time"][:10]
        inst["series"] = series
        inst["clean_date"] = inst_date
        mapped_instances.append(inst)
        
        # Fetch actual participant list
        pcts = fetch_participants_list(inst["uuid"], headers)
        for p in pcts:
            p.update({"series": series, "session_date": inst_date, "webinar_id": inst["id"]})
            all_participants.append(p)
        time.sleep(0.1) # Rate limiting

    df_wb = pd.DataFrame(mapped_instances)
    df_part = pd.DataFrame(all_participants)

    st.title("Digbi Health - Group Coaching Dashboard")
    
    # ── KPIs ──
    k1, k2, k3, k4 = st.columns(4)
    total_sessions = len(df_wb)
    total_att = len(df_part)
    unique_mem = df_part["user_email"].nunique() if not df_part.empty else 0
    
    k1.metric("Total Sessions", total_sessions)
    k2.metric("Total Attendees", total_att)
    k3.metric("Unique Members", unique_mem)
    k4.metric("Avg Sessions/Member", round(total_att/unique_mem, 2) if unique_mem > 0 else 0)

    # ── Table ──
    base_df = pd.DataFrame({"series": COACHING_SERIES})
    wb_counts = df_wb.groupby("series").size().reset_index(name="Sessions")
    
    if not df_part.empty:
        part_stats = df_part.groupby("series").agg(
            Total_Attendees=("user_email", "count"),
            Unique_Members=("user_email", "nunique")
        ).reset_index()
    else:
        part_stats = pd.DataFrame(columns=["series", "Total_Attendees", "Unique_Members"])

    stats_df = pd.merge(base_df, wb_counts, on="series", how="left").fillna(0)
    stats_df = pd.merge(stats_df, part_stats, on="series", how="left").fillna(0)
    stats_df["Avg Sessions / Attendee"] = stats_df.apply(lambda r: round(r["Total_Attendees"]/r["Unique_Members"], 2) if r["Unique_Members"] > 0 else 0, axis=1)

    st.subheader("Stats for 7 Core Coaching Series")
    st.dataframe(stats_df.sort_values("Total_Attendees", ascending=False), use_container_width=True, hide_index=True)

# ── Auth Logic ──
if "token_data" not in st.session_state:
    if "code" in st.query_params:
        st.session_state["token_data"] = exchange_code(st.query_params["code"])
        st.rerun()
    st.title("Digbi Health Dashboard")
    st.markdown(f'<a href="{get_auth_url()}" target="_self" style="background:#FF4B4B;color:white;padding:12px;text-decoration:none;border-radius:6px;">Connect Zoom Account</a>', unsafe_allow_html=True)
else:
    render_dashboard()