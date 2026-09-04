# views/reminders.py
import sqlite3
import pandas as pd
import streamlit as st
from database import get_db, init_db

def ensure_reminders_table():
    """Ensure the reminders table exists with standard schema."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                due_date TEXT,
                task TEXT,
                assigned_to TEXT,
                status TEXT DEFAULT 'OPEN'
            )
        """)
        conn.commit()

def render_reminders(user_name, user_role):
    st.title("📝 Reminders & Tasks")
    st.caption("Track site tasks, equipment inspections, inventory audits, and follow-ups.")

    init_db()
    ensure_reminders_table()

    tab_tasks, tab_add = st.tabs(["📋 Task List", "➕ Create Task / Reminder"])

    # Inspect table schema dynamically
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(reminders)")
        columns = [col[1] for col in cursor.fetchall()]

    # Detect exact task/description column name or default to 'task'
    task_col = "task" if "task" in columns else ("description" if "description" in columns else ("reminder" if "reminder" in columns else "task"))

    # -------------------------------------------------------------
    # TAB 1: TASK LIST & STATUS UPDATES
    # -------------------------------------------------------------
    with tab_tasks:
        try:
            with get_db() as conn:
                query = f"SELECT id, due_date, {task_col} AS task, assigned_to, status FROM reminders ORDER BY due_date ASC, id DESC"
                df = pd.read_sql_query(query, conn)

            if not df.empty:
                # Separate active/open tasks from completed/cancelled tasks
                open_df = df[df["status"].isin(["OPEN", "PENDING"])]
                closed_df = df[df["status"].isin(["COMPLETED", "CANCELLED"])]

                # SECTION 1: OPEN / ACTIVE TASKS
                st.subheader("🟡 Open & Pending Tasks")
                if not open_df.empty:
                    df_open_display = open_df.rename(columns={
                        "id": "ID",
                        "due_date": "Due Date",
                        "task": "Task Description",
                        "assigned_to": "Assigned To",
                        "status": "Status"
                    })
                    st.dataframe(df_open_display, use_container_width=True, hide_index=True)

                    # UPDATE ACTION FORM FOR OPEN TASKS
                    st.markdown("#### 🔄 Update Open Task")
                    with st.form("update_open_task_form"):
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            task_options = [f"#{row['id']} - {row['task']} (Due: {row['due_date']}) [{row['status']}]" for _, row in open_df.iterrows()]
                            selected_task = st.selectbox("Select Task to Update", task_options)

                        with col2:
                            action_type = st.selectbox("Action", ["MARK COMPLETED", "MOVE DUE DATE (RESCHEDULE)", "MARK PENDING", "CANCEL TASK"])
                            
                            new_due_date = None
                            if action_type == "MOVE DUE DATE (RESCHEDULE)":
                                new_due_date = st.date_input("Select New Target Date")

                        submit_update = st.form_submit_button("Submit Update", use_container_width=True)

                        if submit_update and selected_task:
                            task_id = int(selected_task.split("#")[1].split(" ")[0])
                            try:
                                with get_db() as conn:
                                    cursor = conn.cursor()
                                    
                                    if action_type == "MOVE DUE DATE (RESCHEDULE)":
                                        cursor.execute(
                                            "UPDATE reminders SET due_date = ?, status = 'OPEN' WHERE id = ?",
                                            (str(new_due_date), task_id)
                                        )
                                        st.success(f"✅ Task #{task_id} rescheduled to **{new_due_date}**.")
                                    elif action_type == "MARK COMPLETED":
                                        cursor.execute("UPDATE reminders SET status = 'COMPLETED' WHERE id = ?", (task_id,))
                                        st.success(f"✅ Task #{task_id} marked as **COMPLETED**.")
                                    elif action_type == "MARK PENDING":
                                        cursor.execute("UPDATE reminders SET status = 'PENDING' WHERE id = ?", (task_id,))
                                        st.success(f"✅ Task #{task_id} marked as **PENDING**.")
                                    elif action_type == "CANCEL TASK":
                                        cursor.execute("UPDATE reminders SET status = 'CANCELLED' WHERE id = ?", (task_id,))
                                        st.success(f"🚫 Task #{task_id} **CANCELLED**.")

                                    conn.commit()
                                    st.rerun()

                            except Exception as e:
                                st.error(f"Failed to update task: {e}")
                else:
                    st.info("No open or pending tasks currently logged.")

                st.divider()

                # SECTION 2: COMPLETED & CANCELLED TASKS
                st.subheader("✅ Completed & Cancelled History")
                if not closed_df.empty:
                    df_closed_display = closed_df.rename(columns={
                        "id": "ID",
                        "due_date": "Due Date",
                        "task": "Task Description",
                        "assigned_to": "Assigned To",
                        "status": "Status"
                    })
                    st.dataframe(df_closed_display, use_container_width=True, hide_index=True)
                else:
                    st.info("No completed or cancelled tasks in history.")

            else:
                st.info("No task reminders found in the database.")

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
                            cursor.execute(f"""
                                INSERT INTO reminders (due_date, {task_col}, assigned_to, status)
                                VALUES (?, ?, ?, 'OPEN')
                            """, (str(due_date), task_desc.strip(), assigned_to.strip()))
                            conn.commit()
                            st.success(f"✅ Created new task: **{task_desc.strip()}**.")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Failed to save task: {e}")
