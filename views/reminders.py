# views/reminders.py
import sqlite3
import pandas as pd
import streamlit as st
from database import get_db, init_db

def render_reminders(user_name, user_role):
    st.title("📝 Reminders & Tasks")
    st.caption("Track site tasks, equipment inspections, inventory audits, and follow-ups.")

    init_db()

    tab_tasks, tab_add = st.tabs(["📋 Task List", "➕ Create Task / Reminder"])

    # -------------------------------------------------------------
    # TAB 1: TASK LIST & STATUS UPDATES
    # -------------------------------------------------------------
    with tab_tasks:
        st.subheader("Site Tasks Overview")

        filter_status = st.selectbox("Filter Status", ["All", "OPEN", "COMPLETED", "CANCELLED"], key="rem_filter_status")

        # Query omitting optional created_at to avoid schema missing column errors
        query = "SELECT id, due_date, task, assigned_to, status FROM reminders WHERE 1=1"
        params = []

        if filter_status != "All":
            query += " AND status = ?"
            params.append(filter_status)

        query += " ORDER BY due_date ASC, id DESC"

        try:
            with get_db() as conn:
                df = pd.read_sql_query(query, conn, params=params)

            if not df.empty:
                df_display = df.rename(columns={
                    "id": "ID",
                    "due_date": "Due Date",
                    "task": "Task Description",
                    "assigned_to": "Assigned To",
                    "status": "Status"
                })
                st.dataframe(df_display, use_container_width=True, hide_index=True)

                st.divider()
                st.subheader("🔄 Update Task Status")

                with st.form("update_reminder_form"):
                    col1, col2 = st.columns(2)
                    with col1:
                        open_tasks = df[df["status"] == "OPEN"]
                        if not open_tasks.empty:
                            task_options = [f"#{row['id']} - {row['task']} (Due: {row['due_date']})" for _, row in open_tasks.iterrows()]
                            selected_task = st.selectbox("Select Open Task", task_options)
                        else:
                            st.info("No open tasks available to update.")
                            selected_task = None

                    with col2:
                        new_status = st.selectbox("Set Status", ["COMPLETED", "CANCELLED"])

                    submit_update = st.form_submit_button("Update Task Status", use_container_width=True)

                    if submit_update and selected_task:
                        task_id = int(selected_task.split("#")[1].split(" ")[0])
                        try:
                            with get_db() as conn:
                                cursor = conn.cursor()
                                cursor.execute("UPDATE reminders SET status = ? WHERE id = ?", (new_status, task_id))
                                conn.commit()
                                st.success(f"✅ Task #{task_id} marked as '{new_status}'.")
                                st.rerun()
                        except Exception as e:
                            st.error(f"Failed to update task: {e}")
            else:
                st.info("No task reminders found.")

        except Exception as e:
            st.error(f"Error loading tasks: {e}")

    # -------------------------------------------------------------
    # TAB 2: CREATE NEW TASK
    # -------------------------------------------------------------
    with tab_add:
        st.subheader("Create New Task or Reminder")

        with st.form("add_reminder_form", clear_on_submit=True):
            col1, col2 = st.columns(2)

            with col1:
                task_desc = st.text_input("Task Description*", placeholder="e.g., Weekly Fuel Reserve Audit")
                due_date = st.date_input("Target Due Date*")

            with col2:
                assigned_to = st.text_input("Assigned Personnel / Team", value=user_name, placeholder="e.g., Warehouse Team")

            submit_add = st.form_submit_button("💾 Save Task / Reminder", use_container_width=True)

            if submit_add:
                if not task_desc.strip():
                    st.error("⚠️ Task Description is required.")
                else:
                    try:
                        with get_db() as conn:
                            cursor = conn.cursor()
                            cursor.execute("""
                                INSERT INTO reminders (due_date, task, assigned_to, status)
                                VALUES (?, ?, ?, 'OPEN')
                            """, (str(due_date), task_desc.strip(), assigned_to.strip()))
                            conn.commit()
                            st.success(f"✅ Created new task: **{task_desc.strip()}**.")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Failed to save task: {e}")
