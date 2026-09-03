# views/reminders.py
import sqlite3
import pandas as pd
import streamlit as st
from datetime import datetime
from database import get_db

def render_reminders(user_name):
    st.title("📌 Reminders & Site Task Manager")
    st.caption("Keep track of pending reorders, material follow-ups, and site tasks.")

    tab_add, tab_list = st.tabs(["➕ Add New Task", "📋 Active & Completed Tasks"])

    # TAB 1: ADD NEW TASK
    with tab_add:
        st.subheader("Create a Reminder or Task")
        with st.form("add_reminder_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            
            with col1:
                title = st.text_input("Task / Reminder Description", placeholder="e.g., Follow up on Holcim cement delivery")
                due_date = st.date_input("Due Date")
            
            with col2:
                priority = st.selectbox("Priority Level", ["🔴 High", "🟡 Medium", "🟢 Low"])

            submit_reminder = st.form_submit_button("📌 Save Reminder")

            if submit_reminder:
                if not title.strip():
                    st.error("Please enter a task description.")
                else:
                    try:
                        with get_db() as conn:
                            cursor = conn.cursor()
                            cursor.execute("""
                                INSERT INTO reminders (user_name, title, due_date, priority, status, timestamp)
                                VALUES (?, ?, ?, ?, 'PENDING', ?)
                            """, (
                                user_name, 
                                title.strip(), 
                                str(due_date), 
                                priority, 
                                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            ))
                            conn.commit()
                            
                            st.toast("✅ Reminder created successfully!", icon="📌")
                            st.success(f"Task **'{title.strip()}'** logged.")
                            st.rerun()
                    except sqlite3.OperationalError:
                        st.error("Database is busy. Please try again.")

    # TAB 2: ACTIVE & COMPLETED TASKS
    with tab_list:
        st.subheader("Manage Tasks")
        with get_db() as conn:
            df_reminders = pd.read_sql_query(
                "SELECT * FROM reminders ORDER BY status DESC, due_date ASC", 
                conn
            )

        if df_reminders.empty:
            st.info("No reminders or tasks created yet.")
            return

        pending_tasks = df_reminders[df_reminders['status'] == 'PENDING']
        completed_tasks = df_reminders[df_reminders['status'] == 'COMPLETED']

        st.markdown(f"#### ⏳ Pending Tasks ({len(pending_tasks)})")
        if not pending_tasks.empty:
            for _, row in pending_tasks.iterrows():
                col1, col2, col3 = st.columns([4, 2, 1])
                with col1:
                    st.markdown(f"**{row['title']}**")
                    st.caption(f"Priority: {row['priority']} | Due: `{row['due_date']}` | Created by: `{row['user_name']}`")
                with col2:
                    st.write("")
                with col3:
                    if st.button("Mark Done", key=f"done_{row['id']}"):
                        with get_db() as conn:
                            cursor = conn.cursor()
                            cursor.execute("UPDATE reminders SET status = 'COMPLETED' WHERE id = ?", (row['id'],))
                            conn.commit()
                            st.toast("✅ Task marked as completed!")
                            st.rerun()
                st.divider()
        else:
            st.success("🎉 All tasks are currently completed!")

        if not completed_tasks.empty:
            with st.expander(f"✅ View Completed Tasks ({len(completed_tasks)})"):
                display_completed = completed_tasks[['title', 'due_date', 'priority', 'user_name']].rename(columns={
                    "title": "Task",
                    "due_date": "Due Date",
                    "priority": "Priority",
                    "user_name": "Created By"
                })
                st.dataframe(display_completed, use_container_width=True, hide_index=True)
