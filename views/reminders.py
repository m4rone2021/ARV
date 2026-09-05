from datetime import datetime, date
import pandas as pd
import streamlit as st
from database import get_db


def ensure_reminders_table():
    """Ensure the reminders table exists with required columns cleanly."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    due_date TEXT,
                    task TEXT,
                    assigned_to TEXT,
                    status TEXT DEFAULT 'OPEN',
                    priority TEXT DEFAULT 'NORMAL'
                )
                """
            )

            cursor.execute("PRAGMA table_info(reminders)")
            cols = [col[1] for col in cursor.fetchall()]

            if "priority" not in cols:
                cursor.execute(
                    "ALTER TABLE reminders ADD COLUMN priority TEXT DEFAULT 'NORMAL'"
                )
            if "task" not in cols and "description" in cols:
                cursor.execute(
                    "ALTER TABLE reminders RENAME COLUMN description TO task"
                )

            conn.commit()
    except Exception as e:
        st.error(f"Failed to initialize reminders table: {e}")


def calculate_days_left(due_date_str):
    """Calculate days remaining from today until the due date."""
    if not due_date_str:
        return 9999, "No Date"
    try:
        due_dt = datetime.strptime(str(due_date_str).strip(), "%Y-%m-%d").date()
        today = date.today()
        days_diff = (due_dt - today).days

        if days_diff < 0:
            return days_diff, f"🔴 OVERDUE ({abs(days_diff)}d ago)"
        elif days_diff == 0:
            return days_diff, "🟠 DUE TODAY"
        elif days_diff == 1:
            return days_diff, "🟡 1 day left"
        else:
            return days_diff, f"🟢 {days_diff} days left"
    except Exception:
        return 9999, "Invalid Date"


def render_reminders(user_name, user_role):
    st.title("📝 Reminders & Tasks")

    # Table setup
    ensure_reminders_table()

    # Access control evaluation
    is_admin = user_role.lower() in ["admin", "manager"] if user_role else False

    if is_admin:
        st.caption(
            f"👑 **Admin Mode** ({user_name}): Viewing and managing **all** site tasks."
        )
    else:
        st.caption(
            f"👤 **User Mode** ({user_name}): Viewing tasks assigned specifically to you."
        )

    tab_tasks, tab_add = st.tabs(["📋 Task List", "➕ Create Task / Reminder"])

    # -------------------------------------------------------------
    # TAB 1: TASK LIST & STATUS UPDATES
    # -------------------------------------------------------------
    with tab_tasks:
        try:
            with get_db() as conn:
                if is_admin:
                    query = """
                        SELECT id, due_date, task, assigned_to, status, priority 
                        FROM reminders
                    """
                    params = []
                else:
                    query = """
                        SELECT id, due_date, task, assigned_to, status, priority 
                        FROM reminders 
                        WHERE LOWER(assigned_to) = LOWER(?)
                    """
                    params = [user_name.strip()]

                df = pd.read_sql_query(query, conn, params=params)

            if not df.empty:
                days_left_data = df["due_date"].apply(calculate_days_left)
                df["days_left_num"] = [d[0] for d in days_left_data]
                df["days_left_str"] = [d[1] for d in days_left_data]

                open_df = df[df["status"].isin(["OPEN", "PENDING"])].copy()
                closed_df = df[df["status"].isin(["COMPLETED", "CANCELLED"])].copy()

                # SECTION 1: OPEN / ACTIVE TASKS
                st.subheader("🟡 Open & Pending Tasks")
                if not open_df.empty:
                    open_df = open_df.sort_values(
                        by=["days_left_num", "priority"],
                        ascending=[True, False],
                    )

                    open_df["Priority Display"] = open_df["priority"].apply(
                        lambda x: "🚨 HIGH" if x == "HIGH" else "NORMAL"
                    )

                    df_open_display = open_df[
                        [
                            "id",
                            "due_date",
                            "days_left_str",
                            "Priority Display",
                            "task",
                            "assigned_to",
                            "status",
                        ]
                    ].rename(
                        columns={
                            "id": "ID",
                            "due_date": "Due Date",
                            "days_left_str": "Days Left",
                            "Priority Display": "Priority",
                            "task": "Task Description",
                            "assigned_to": "Assigned To",
                            "status": "Status",
                        }
                    )
                    st.dataframe(
                        df_open_display,
                        use_container_width=True,
                        hide_index=True,
                    )

                    # UPDATE ACTION FORM
                    st.markdown("#### 🔄 Update Task Status / Schedule")
                    with st.form("update_open_task_form", clear_on_submit=False):
                        col1, col2 = st.columns(2)

                        with col1:
                            task_options = {
                                f"#{row['id']} [{row['priority']}] - {row['task']} ({row['days_left_str']})": row[
                                    "id"
                                ]
                                for _, row in open_df.iterrows()
                            }
                            selected_label = st.selectbox(
                                "Select Task to Update",
                                list(task_options.keys()),
                            )

                        with col2:
                            action_type = st.selectbox(
                                "Action",
                                [
                                    "MARK COMPLETED",
                                    "MOVE DUE DATE (RESCHEDULE)",
                                    "SET AS HIGH PRIORITY",
                                    "SET AS NORMAL PRIORITY",
                                    "MARK PENDING",
                                    "CANCEL TASK",
                                ],
                            )
                            new_due_date = st.date_input(
                                "Select New Target Date (If Rescheduling)",
                                value=date.today(),
                            )

                        submit_update = st.form_submit_button(
                            "Submit Update", use_container_width=True
                        )

                        if submit_update and selected_label:
                            task_id = task_options[selected_label]
                            try:
                                with get_db() as conn:
                                    cursor = conn.cursor()

                                    if action_type == "MOVE DUE DATE (RESCHEDULE)":
                                        cursor.execute(
                                            "UPDATE reminders SET due_date = ?, status = 'OPEN' WHERE id = ?",
                                            (str(new_due_date), task_id),
                                        )
                                    elif action_type == "SET AS HIGH PRIORITY":
                                        cursor.execute(
                                            "UPDATE reminders SET priority = 'HIGH' WHERE id = ?",
                                            (task_id,),
                                        )
                                    elif action_type == "SET AS NORMAL PRIORITY":
                                        cursor.execute(
                                            "UPDATE reminders SET priority = 'NORMAL' WHERE id = ?",
                                            (task_id,),
                                        )
                                    elif action_type == "MARK COMPLETED":
                                        cursor.execute(
                                            "UPDATE reminders SET status = 'COMPLETED' WHERE id = ?",
                                            (task_id,),
                                        )
                                    elif action_type == "MARK PENDING":
                                        cursor.execute(
                                            "UPDATE reminders SET status = 'PENDING' WHERE id = ?",
                                            (task_id,),
                                        )
                                    elif action_type == "CANCEL TASK":
                                        cursor.execute(
                                            "UPDATE reminders SET status = 'CANCELLED' WHERE id = ?",
                                            (task_id,),
                                        )

                                    conn.commit()
                                st.success(f"Task #{task_id} updated successfully!")
                                st.rerun()

                            except Exception as e:
                                st.error(f"Failed to update task: {e}")
                else:
                    st.info(
                        "No open or pending tasks assigned to you."
                        if not is_admin
                        else "No open tasks in the database."
                    )

                st.divider()

                # SECTION 2: COMPLETED & CANCELLED TASKS
                st.subheader("✅ Completed & Cancelled History")
                if not closed_df.empty:
                    closed_df = closed_df.sort_values(by="id", ascending=False)
                    df_closed_display = closed_df[
                        ["id", "due_date", "task", "assigned_to", "status"]
                    ].rename(
                        columns={
                            "id": "ID",
                            "due_date": "Due Date",
                            "task": "Task Description",
                            "assigned_to": "Assigned To",
                            "status": "Status",
                        }
                    )
                    st.dataframe(
                        df_closed_display,
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.info("No completed or cancelled tasks found.")

            else:
                st.info(
                    "No task reminders recorded for your user account."
                    if not is_admin
                    else "No task reminders registered in the system."
                )

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
                task_desc = st.text_input(
                    "Task Description*",
                    placeholder="e.g., Weekly Fuel Reserve Audit",
                )
                due_date = st.date_input("Target Due Date*", value=date.today())

            with col2:
                assigned_to = st.text_input(
                    "Assigned Personnel / Team",
                    value=user_name,
                    placeholder="e.g., Warehouse Team",
                )
                is_high_priority = st.checkbox("🚨 Mark as High Priority", value=False)

            submit_add = st.form_submit_button(
                "💾 Save Task / Reminder", use_container_width=True
            )

            if submit_add:
                if not task_desc.strip():
                    st.error("⚠️ Task Description is required.")
                else:
                    try:
                        priority_val = "HIGH" if is_high_priority else "NORMAL"
                        with get_db() as conn:
                            cursor = conn.cursor()
                            cursor.execute(
                                """
                                INSERT INTO reminders (due_date, task, assigned_to, status, priority)
                                VALUES (?, ?, ?, 'OPEN', ?)
                                """,
                                (
                                    str(due_date),
                                    task_desc.strip(),
                                    assigned_to.strip(),
                                    priority_val,
                                ),
                            )
                            conn.commit()
                        st.success(
                            f"Task assigned to **{assigned_to.strip()}**: **{task_desc.strip()}**"
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to save task: {e}")
