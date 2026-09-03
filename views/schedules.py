# views/schedules.py
import sqlite3
import pandas as pd
import streamlit as st
from datetime import datetime
from database import get_db

def render_schedules(user_name):
    st.title("📅 Site Schedules & Delivery Calendar")
    st.caption("Plan and schedule site deliveries, equipment arrivals, and material inspections.")

    tab_add, tab_list = st.tabs(["➕ Schedule New Event", "📅 Event Calendar & Agenda"])

    # TAB 1: SCHEDULE NEW EVENT
    with tab_add:
        st.subheader("Log a Scheduled Event")
        with st.form("add_schedule_form", clear_on_submit=True):
            col1, col2 = st.columns(2)

            with col1:
                title = st.text_input("Event Title / Delivery Notice", placeholder="e.g., 500 Bags Cement Delivery - Holcim")
                event_date = st.date_input("Event Date")
                location = st.text_input("Site Location / Drop Zone", placeholder="e.g., Main Gate - Unloading Area B")

            with col2:
                start_time = st.time_input("Start Time")
                end_time = st.time_input("End Time")
                notes = st.text_area("Additional Notes / Contact Person", placeholder="e.g., Contact Engineer Mark upon arrival")

            submit_schedule = st.form_submit_button("📅 Add to Schedule")

            if submit_schedule:
                if not title.strip():
                    st.error("Please provide an event title.")
                else:
                    try:
                        with get_db() as conn:
                            cursor = conn.cursor()
                            cursor.execute("""
                                INSERT INTO schedules (
                                    user_name, title, event_date, start_time, end_time, location_details, notes, timestamp
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                user_name,
                                title.strip(),
                                str(event_date),
                                str(start_time),
                                str(end_time),
                                location.strip(),
                                notes.strip(),
                                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            ))
                            conn.commit()

                            st.toast("✅ Scheduled event saved successfully!", icon="📅")
                            st.success(f"Event **'{title.strip()}'** scheduled for **{event_date}**.")
                            st.rerun()
                    except sqlite3.OperationalError:
                        st.error("Database is busy. Please try again.")

    # TAB 2: SCHEDULE AGENDA
    with tab_list:
        st.subheader("Upcoming Schedules")
        with get_db() as conn:
            df_schedules = pd.read_sql_query(
                "SELECT * FROM schedules ORDER BY event_date ASC, start_time ASC", 
                conn
            )

        if df_schedules.empty:
            st.info("No events or deliveries currently scheduled.")
            return

        display_df = df_schedules[[
            'event_date', 'start_time', 'end_time', 'title', 'location_details', 'notes', 'user_name'
        ]].rename(columns={
            "event_date": "Date",
            "start_time": "Start Time",
            "end_time": "End Time",
            "title": "Event Title",
            "location_details": "Location / Gate",
            "notes": "Notes",
            "user_name": "Scheduled By"
        })

        st.dataframe(display_df, use_container_width=True, hide_index=True)
