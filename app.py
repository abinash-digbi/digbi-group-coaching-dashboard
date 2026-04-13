"""
Digbi Health — Group Coaching Dashboard
Version: Diagnostic Mode (Fixed Case Sensitivity)
"""

import streamlit as st
import pandas as pd
import requests
import json
from datetime import date

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
    if not isinstance(topic_str, str): return "Unmapped"
    t = topic_str.strip().lower()
    
    excluded = ["schreiber", "dexcom", "kehe", "ndphit", "silgan", "okaloosa", "azlgebt", "frp", "evry health", "raght", "mohave", "sscgp", "southern", "weston", "prism", "zachry", "city of fw", "city of fort worth", "aaa", "elbit", "vericast", "dexter", "west fargo", "naebt", "cct", "southern star"]
    if any(k in t for k in excluded): return "Excluded Client Session"

    if "group coaching for members" in t: return COACHING_SERIES[0]
    if "join our group coaching session" in t: return COACHING_SERIES[1]
    if "genetics" in t or "nutrition" in t: return COACHING_SERIES[2]
    if "instincts" in t or "microbiome" in t: return COACHING_SERIES[3]
    if "glp" in t or "wellness benefit" in t or "living well" in t: return COACHING_SERIES[4]
    if "ibs" in t or "irritable" in t: return COACHING_SERIES[5]
    if "fine-tuning" in t or "fine tuning" in t: return COACHING_SERIES[6]
    
    return "Unmapped"

# 3. DATABASE HELPER FUNCTIONS
@st.cache_data(ttl=60, show_spinner=False)
def load_database():
    try:
        r = requests.get(APPS_SCRIPT_URL)
        if r.status_code == 200:
            data = r.json()
            if len(data) > 1: 
                df = pd.DataFrame(data[1:], columns=data[0])
                df['Temp_Date'] = pd.to_datetime(df['Start Time'], errors='coerce')
                df = df.sort_values(by='Temp_Date', ascending=True).drop(columns=['Temp_Date'])
                return df.reset_index(drop=True)
        return pd.DataFrame(columns=["Session ID", "Topic", "Mapped Series", "Start Time", "Participant Email", "Source"])
    except:
        return pd.DataFrame(columns=["Session ID", "Topic", "Mapped Series", "Start Time", "Participant Email", "Source"])

def process_and_upload(uploaded_files, existing_df):
    new_rows = []
    
    for file in uploaded_files:
        try: df = pd.read_csv(file)
        except Exception: continue
            
        if 'Topic' not in df.columns: continue
            
        start_time_col = 'Start time' if 'Start time' in df.columns else ('Start Time' if 'Start Time' in df.columns else None)
        id_col = 'ID' if 'ID' in df.columns else ('Meeting ID' if 'Meeting ID' in df.columns else None)
        
        if not start_time_col or not id_col: continue
            
        for _, row in df.iterrows():
            mapped = map_to_series(row['Topic'])
            
            s_id = str(row[id_col]).replace(" ", "")
            s_time = str(row[start_time_col])
            
            email_val = 'no email'
            if 'Email' in df.columns and pd.notna(row['Email']): email_val = row['Email']
            elif 'User Email' in df.columns and pd.notna(row['User Email']): email_val = row['User Email']
            email = str(email_val).strip().lower()
            
            name_val = 'unknown_user'
            # FIXED: Made column checking highly robust for case sensitivity and Zoom variations
            if 'Name (Original Name)' in df.columns and pd.notna(row['Name (Original Name)']): name_val = row['Name (Original Name)']
            elif 'Name (original name)' in df.columns and pd.notna(row['Name (original name)']): name_val = row['Name (original name)']
            elif 'Name' in df.columns and pd.notna(row['Name']): name_val = row['Name']
            elif 'First Name' in df.columns: name_val = str(row.get('First Name', '')) + "_" + str(row.get('Last Name', ''))
            
            if email == 'no email' or email == '':
                email = f"no_email_{str(name_val).strip().lower().replace(' ', '_')}_{s_id[-4:]}"
            
            is_dup = False
            if not existing_df.empty:
                match = existing_df[(existing_df['Session ID'].astype(str) == s_id) & 
                                    (existing_df['Start Time'] == s_time) & 
                                    (existing_df['Participant Email'] == email)]
                if not match.empty: is_dup = True
            
            if not is_dup:
                new_rows.append([s_id, row['Topic'], mapped, s_time, email, file.name])
                existing_df.loc[len(existing_df)] = new_rows[-1] 
                
    if new_rows:
        try:
            r = requests.post(APPS_SCRIPT_URL, json=new_rows)
            return len(new_rows)
        except Exception as e:
            return 0
    return 0

# 4. DASHBOARD UI
def render_dashboard():
    # -- SIDEBAR UPLOADER --
    st.sidebar.title("📤 Monthly Data Importer")
    uploaded_files = st.sidebar.file_uploader("Upload CSVs", type=['csv'], accept_multiple_files=True)
    db_df = load_database()
    
    if st.sidebar.button("Sync to Google Sheets"):
        if uploaded_files:
            with st.spinner("Validating and Saving..."):
                added = process_and_upload(uploaded_files, db_df)
            if added > 0:
                st.sidebar.success(f"✅ Successfully added {added} new records!")
            st.cache_data.clear() 
            st.rerun()

    # -- SIDEBAR DATE FILTERS --
    st.sidebar.markdown("---")
    st.sidebar.title("📅 Dashboard Filters")
    start_date = st.sidebar.date_input("Start Date", value=date(2026, 1, 1))
    end_date = st.sidebar.date_input("End Date", value=date.today())

    st.title("Digbi Health - Coaching Dashboard")
    
    if db_df.empty:
        st.info("The database is currently empty. Upload your historical CSVs on the left to build the dashboard.")
        return

    # FILTER DATA BY SELECTED DATES
    db_df['Clean_Date'] = pd.to_datetime(db_df['Start Time'], errors='coerce').dt.date
    mask = (db_df['Clean_Date'] >= start_date) & (db_df['Clean_Date'] <= end_date)
    filtered_db = db_df.loc[mask].copy()

    if filtered_db.empty:
        st.warning(f"No sessions found between {start_date} and {end_date}.")
        return

    # ── DATA BUCKETS ──
    df_all_sessions = filtered_db.drop_duplicates(subset=['Session ID', 'Start Time']).copy()
    
    df_core_sessions = df_all_sessions[df_all_sessions['Mapped Series'].isin(COACHING_SERIES)]
    # FIXED: Re-enabled phone numbers to show in Attendee count
    df_core_attendees = filtered_db[(filtered_db['Mapped Series'].isin(COACHING_SERIES)) & 
                                    (~filtered_db['Participant Email'].str.startswith('no_email_unknown_user'))]

    df_unmapped = df_all_sessions[df_all_sessions['Mapped Series'] == 'Unmapped']
    df_excluded = df_all_sessions[df_all_sessions['Mapped Series'] == 'Excluded Client Session']

    # Master KPIs
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Group Coaching Sessions", len(df_core_sessions))
    c2.metric("Total Attendees", len(df_core_attendees))
    c3.metric("Excluded (Client) Sessions", len(df_excluded))
    c4.metric("Unmapped/Unknown Sessions", len(df_unmapped))

    if not df_unmapped.empty:
        st.error(f"⚠️ DATA LEAK DETECTED: {len(df_unmapped)} Sessions are missing from the tables below because their Topic names did not match our keywords.")
        with st.expander("View Unmapped Sessions (Click here to find missing data)"):
            st.dataframe(df_unmapped[['Start Time', 'Topic', 'Session ID']])

    st.markdown("---")

    # ── 1. AGGREGATE PERFORMANCE TABLE ──
    st.subheader("Core Series Performance")
    base = pd.DataFrame({"series": COACHING_SERIES})
    counts = df_core_sessions.groupby("Mapped Series").size().reset_index(name="Sessions")
    
    if not df_core_attendees.empty:
        stats = df_core_attendees.groupby("Mapped Series").agg(Attendees=("Participant Email", "count"), Unique=("Participant Email", "nunique")).reset_index()
    else:
        stats = pd.DataFrame(columns=["Mapped Series", "Attendees", "Unique"])

    merged = pd.merge(base, counts, left_on="series", right_on="Mapped Series", how="left").fillna(0)
    merged = pd.merge(merged, stats, left_on="series", right_on="Mapped Series", how="left").fillna(0)
    
    merged["Avg Attendance"] = (merged["Attendees"] / merged["Sessions"].replace(0, float('nan'))).fillna(0).round(1)
    st.dataframe(merged[["series", "Sessions", "Attendees", "Unique", "Avg Attendance"]].sort_values("Sessions", ascending=False), use_container_width=True, hide_index=True)

    st.markdown("---")

    # ── 2. DEEP DIVE: GRAPHS & FILTERS ──
    st.header("📈 Series Deep Dive")
    
    if not df_core_attendees.empty:
        session_counts = df_core_attendees.groupby(['Session ID', 'Start Time']).size().reset_index(name='Participants')
    else:
        session_counts = pd.DataFrame(columns=['Session ID', 'Start Time', 'Participants'])

    df_breakdown = pd.merge(df_core_sessions, session_counts, on=['Session ID', 'Start Time'], how='left')
    df_breakdown['Participants'] = df_breakdown['Participants'].fillna(0).astype(int)
    df_breakdown['Date'] = pd.to_datetime(df_breakdown['Start Time'], errors='coerce').dt.date

    series_options = [s for s in COACHING_SERIES if s in df_breakdown['Mapped Series'].values]
    selected_series = st.selectbox("Select Coaching Series:", ["-- Choose a Series to view details --"] + series_options)

    if selected_series != "-- Choose a Series to view details --":
        filtered_series_df = df_breakdown[df_breakdown['Mapped Series'] == selected_series].sort_values("Date", ascending=True)
        
        total_sesh = len(filtered_series_df)
        total_att = filtered_series_df['Participants'].sum()
        unique_att = df_core_attendees[df_core_attendees['Mapped Series'] == selected_series]['Participant Email'].nunique()
        
        mc1, mc2, mc3 = st.columns(3)
        mc1.metric(f"Total Sessions", total_sesh)
        mc2.metric("Total Attendees", total_att)
        mc3.metric("Unique Members", unique_att)

        st.subheader("Attendance Trend Over Time")
        # FIX: Group by specific Start Time so same-day sessions get their own separate bars
        chart_data = filtered_series_df[['Start Time', 'Participants']].copy()
        chart_data.set_index('Start Time', inplace=True)
        st.bar_chart(chart_data, color="#FF4B4B")

        st.subheader("Detailed Session Log")
        display_cols = ['Date', 'Start Time', 'Topic', 'Participants']
        st.dataframe(filtered_series_df[display_cols].sort_values("Date", ascending=True), use_container_width=True, hide_index=True)

    # ── DEBUG RAW DB ──
    st.markdown("---")
    with st.expander("View Complete Raw Database (See everything loaded into Google Sheets)"):
        st.dataframe(db_df.drop(columns=['Clean_Date']))

render_dashboard()