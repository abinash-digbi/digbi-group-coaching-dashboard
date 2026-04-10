"""
Digbi Health — Group Coaching Dashboard
Version: Google Sheets Database + Participant Breakdown
"""

import streamlit as st
import pandas as pd
import requests
import json

# 1. SETUP
st.set_page_config(page_title="Digbi Analytics", page_icon="🧬", layout="wide")

try:
    APPS_SCRIPT_URL = st.secrets["APPS_SCRIPT_URL"]
except KeyError:
    st.error("Please add APPS_SCRIPT_URL to your Streamlit Secrets.")
    st.stop()

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

# 3. DATABASE HELPER FUNCTIONS
@st.cache_data(ttl=60, show_spinner=False)
def load_database():
    """Fetches existing data from Google Sheets via Apps Script"""
    try:
        r = requests.get(APPS_SCRIPT_URL)
        if r.status_code == 200:
            data = r.json()
            if len(data) > 1: # We have data beyond the header
                df = pd.DataFrame(data[1:], columns=data[0])
                return df
        return pd.DataFrame(columns=["Session ID", "Topic", "Mapped Series", "Start Time", "Participant Email", "Source"])
    except:
        return pd.DataFrame(columns=["Session ID", "Topic", "Mapped Series", "Start Time", "Participant Email", "Source"])

def process_and_upload(uploaded_files, existing_df):
    """Parses CSVs, prevents duplicates, and sends to Google Sheets safely"""
    new_rows = []
    
    for file in uploaded_files:
        df = pd.read_csv(file)
        
        # Make column checking more flexible to account for Zoom format changes
        if 'Topic' not in df.columns:
            continue
            
        start_time_col = 'Start time' if 'Start time' in df.columns else 'Start Time'
        id_col = 'ID' if 'ID' in df.columns else 'Meeting ID'
        
        if start_time_col not in df.columns or id_col not in df.columns:
            continue
            
        for _, row in df.iterrows():
            mapped = map_to_series(row['Topic'])
            if mapped == "Other": continue
            
            s_id = str(row[id_col]).replace(" ", "")
            s_time = str(row[start_time_col])
            
            # Look for Email or User Email columns
            email_val = 'no email'
            if 'Email' in df.columns and pd.notna(row['Email']): email_val = row['Email']
            elif 'User Email' in df.columns and pd.notna(row['User Email']): email_val = row['User Email']
            email = str(email_val).strip().lower()
            
            # Prevent Duplicates
            is_dup = False
            if not existing_df.empty:
                match = existing_df[(existing_df['Session ID'].astype(str) == s_id) & 
                                    (existing_df['Start Time'] == s_time) & 
                                    (existing_df['Participant Email'] == email)]
                if not match.empty:
                    is_dup = True
            
            if not is_dup:
                new_rows.append([s_id, row['Topic'], mapped, s_time, email, file.name])
                existing_df.loc[len(existing_df)] = new_rows[-1] 
                
    if new_rows:
        # Send to Google Apps Script and check the exact response!
        try:
            # Using json=new_rows ensures the format is perfectly read by Google
            r = requests.post(APPS_SCRIPT_URL, json=new_rows)
            
            # If Google sends back an error message, show it to the user
            if "error" in r.text.lower():
                st.error(f"Google Apps Script Error: {r.text}")
                return 0
                
            return len(new_rows)
        except Exception as e:
            st.error(f"Failed to connect to Google Sheets: {e}")
            return 0
            
    return 0

# 4. DASHBOARD UI
def render_dashboard():
    # -- SIDEBAR UPLOADER --
    st.sidebar.title("📤 Monthly Data Importer")
    st.sidebar.write("Drag and drop your Zoom CSV reports here. They will be saved to your Google Sheet.")
    
    uploaded_files = st.sidebar.file_uploader("Upload CSVs", type=['csv'], accept_multiple_files=True)
    
    db_df = load_database()
    
    if st.sidebar.button("Sync to Google Sheets"):
        if uploaded_files:
            with st.spinner("Processing files and saving to Database..."):
                added = process_and_upload(uploaded_files, db_df)
            st.sidebar.success(f"✅ Successfully added {added} new records!")
            st.cache_data.clear() # Force refresh to show new data
            st.rerun()
        else:
            st.sidebar.error("Upload files first!")

    # -- MAIN DASHBOARD --
    st.title("Digbi Health - Group Coaching Master Dashboard")
    
    if db_df.empty:
        st.info("The database is currently empty. Upload your historical CSVs on the left to build the dashboard.")
        return

    # Calculate Metrics
    df_sessions = db_df.drop_duplicates(subset=['Session ID', 'Start Time']).copy()
    df_attendees = db_df[db_df['Participant Email'] != 'no email']

    # KPIs
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Tracked Sessions", len(df_sessions))
    c2.metric("Total Attendees", len(df_attendees))
    c3.metric("Unique Members", df_attendees['Participant Email'].nunique() if not df_attendees.empty else 0)

    st.markdown("---")

    # ── 1. AGGREGATE PERFORMANCE TABLE ──
    st.subheader("Aggregate Series Performance")
    base = pd.DataFrame({"series": COACHING_SERIES})
    
    counts = df_sessions.groupby("Mapped Series").size().reset_index(name="Sessions")
    
    if not df_attendees.empty:
        stats = df_attendees.groupby("Mapped Series").agg(Attendees=("Participant Email", "count"), Unique=("Participant Email", "nunique")).reset_index()
    else:
        stats = pd.DataFrame(columns=["Mapped Series", "Attendees", "Unique"])

    merged = pd.merge(base, counts, left_on="series", right_on="Mapped Series", how="left").fillna(0)
    merged = pd.merge(merged, stats, left_on="series", right_on="Mapped Series", how="left").fillna(0)
    merged["Avg Attendance"] = (merged["Attendees"] / merged["Sessions"].replace(0, float('nan'))).fillna(0).round(1)    
    st.dataframe(merged[["series", "Sessions", "Attendees", "Unique", "Avg Attendance"]].sort_values("Sessions", ascending=False), use_container_width=True, hide_index=True)

    st.markdown("---")

    # ── 2. INDIVIDUAL SESSION BREAKDOWN ──
    st.subheader("👥 Participants per Session")
    st.write("A detailed view of how many members attended each specific date/time.")
    
    if not df_attendees.empty:
        session_counts = df_attendees.groupby(['Session ID', 'Start Time']).size().reset_index(name='Participants')
    else:
        session_counts = pd.DataFrame(columns=['Session ID', 'Start Time', 'Participants'])

    df_breakdown = pd.merge(df_sessions, session_counts, on=['Session ID', 'Start Time'], how='left')
    df_breakdown['Participants'] = df_breakdown['Participants'].fillna(0).astype(int)

    # Sort so newest sessions are at the top
    df_breakdown['Sort_Date'] = pd.to_datetime(df_breakdown['Start Time'], errors='coerce')
    df_breakdown = df_breakdown.sort_values(by='Sort_Date', ascending=False).drop(columns=['Sort_Date'])

    display_cols = ['Start Time', 'Topic', 'Mapped Series', 'Participants', 'Session ID']
    st.dataframe(df_breakdown[display_cols], use_container_width=True, hide_index=True)

    # ── DEBUG RAW DB ──
    with st.expander("View Underlying Google Sheets Database"):
        st.dataframe(db_df.sort_values("Start Time", ascending=False))

render_dashboard()