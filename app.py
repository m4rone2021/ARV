import sqlite3
from contextlib import contextmanager
import pandas as pd
import streamlit as st

# -------------------------------------------------------------
# PAGE CONFIGURATION
# -------------------------------------------------------------
st.set_page_config(
    page_title="ARV Inventory System",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_NAME = "inventory.db"

# -------------------------------------------------------------
# DATABASE FUNCTIONS
# -------------------------------------------------------------
@contextmanager
def get_db():
    """Provides a transactional database connection context."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    """Initializes schema and ensures default admin user exists."""
    with get_db() as conn:
        cursor = conn.cursor()

        # Master Items Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS master_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT UNIQUE NOT NULL,
                category TEXT NOT NULL,
                unit TEXT NOT NULL,
                current_stock REAL DEFAULT 0,
                min_threshold REAL DEFAULT 10,
                remarks TEXT
            )
        """)

        # Transactions Table (Stock In / Stock Out history)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                type TEXT NOT NULL,
                item_name TEXT NOT NULL,
                quantity REAL NOT NULL,
                unit TEXT NOT NULL,
                handled_by TEXT NOT NULL,
                notes TEXT
            )
        """)

        # Deliveries Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT NOT NULL,
                supplier_or_destination TEXT NOT NULL,
                quantity REAL NOT NULL,
                unit TEXT NOT NULL,
                scheduled_date TEXT NOT NULL,
                status TEXT DEFAULT 'Pending',
                notes TEXT,
                created_by TEXT
            )
        """)

        # Users Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL
            )
        """)

        # Ensure default Admin credentials (admin / admin123)
        cursor.execute("SELECT id FROM users WHERE username = 'admin'")
        existing_admin = cursor.fetchone()

        if existing_admin:
            cursor.execute("""
                UPDATE users 
                SET password = 'admin123', role = 'Admin' 
                WHERE username = 'admin'
            """)
        else:
            cursor.execute("""
                INSERT INTO users (username, password, role) 
                VALUES ('admin', 'admin123', 'Admin')
            """)

        conn.commit()

# Initialize Database on app load
init_db()

# -------------------------------------------------------------
# SESSION STATE SETUP
# -------------------------------------------------------------
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "user_name" not in st.session_state:
    st.session_state.user_name = ""
if "user_role" not in st.session_state:
    st.session_state.user_role = ""

# -------------------------------------------------------------
# MODULE VIEWS
# -------------------------------------------------------------

def render_manage_items(user_name, user_role):
    st.title("📂 Manage Items")
    st.caption("Add, view, and manage master item catalog and thresholds.")

    tab_view, tab_add = st.tabs(["📋 Item Catalog", "➕ Add New Item"])

    with tab_view:
        try:
            with get_db() as conn:
                df = pd.read_sql_query("SELECT id, item_name, category, current_stock, unit, min_threshold, remarks FROM master_items ORDER BY item_name ASC", conn)
            
            if not df.empty:
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("No items found in the catalog. Add some items using the 'Add New Item' tab.")
        except Exception as e:
            st.error(f"Error loading items: {e}")

    with tab_add:
        with st.form("add_item_form"):
            col1, col2 = st.columns(2)
            with col1:
                item_name = st.text_input("Item Name*").strip()
                category = st.text_input("Category*", placeholder="e.g., Construction, Hardware").strip()
            with col2:
                unit = st.text_input("Unit*", placeholder="e.g., pcs, kg, bags").strip()
                min_threshold = st.number_input("Min Threshold*", min_value=0.0, value=10.0)

            remarks = st.text_input("Remarks / Description")
            submit = st.form_submit_button("➕ Add Item", use_container_width=True)

            if submit:
                if not item_name or not category or not unit:
                    st.error("⚠️ Please fill in all required fields.")
                else:
                    try:
                        with get_db() as conn:
                            cursor = conn.cursor()
                            cursor.execute("""
                                INSERT INTO master_items (item_name, category, unit, current_stock, min_threshold, remarks)
                                VALUES (?, ?, ?, 0, ?, ?)
                            """, (item_name, category, unit, min_threshold, remarks))
                            conn.commit()
                            st.success(f"Item **{item_name}** added successfully!")
                            st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("An item with this name already exists.")
                    except Exception as e:
                        st.error(f"Failed to add item: {e}")


def render_stock_in(user_name, user_role):
    st.title("📥 Stock In")
    st.caption("Receive items into inventory and update stock counts.")

    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT item_name, unit FROM master_items ORDER BY item_name ASC")
            items = cursor.fetchall()

        if not items:
            st.warning("No items available. Please add items in 'Manage Items' first.")
            return

        item_names = [item["item_name"] for item in items]
        units_map = {item["item_name"]: item["unit"] for item in items}

        with st.form("stock_in_form"):
            selected_item = st.selectbox("Select Item*", item_names)
            unit_display = units_map.get(selected_item, "")
            
            quantity = st.number_input(f"Quantity to Receive ({unit_display})*", min_value=0.01, value=1.0, step=1.0)
            notes = st.text_input("Notes / Reference No.", placeholder="e.g., PO-12345")
            
            submit = st.form_submit_button("📥 Receive Stock", use_container_width=True)

            if submit:
                try:
                    with get_db() as conn:
                        cursor = conn.cursor()
                        cursor.execute("UPDATE master_items SET current_stock = current_stock + ? WHERE item_name = ?", (quantity, selected_item))
                        cursor.execute("""
                            INSERT INTO transactions (type, item_name, quantity, unit, handled_by, notes)
                            VALUES ('STOCK_IN', ?, ?, ?, ?, ?)
                        """, (selected_item, quantity, unit_display, user_name, notes))
                        conn.commit()
                        st.success(f"Successfully added {quantity} {unit_display} to **{selected_item}**!")
                        st.rerun()
                except Exception as e:
                    st.error(f"Error processing stock in: {e}")
    except Exception as e:
        st.error(f"Error loading items: {e}")


def render_stock_out(user_name, user_role):
    st.title("📤 Stock Out")
    st.caption("Dispatch items from inventory and update stock counts.")

    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT item_name, current_stock, unit FROM master_items ORDER BY item_name ASC")
            items = cursor.fetchall()

        if not items:
            st.warning("No items available in the catalog.")
            return

        item_names = [item["item_name"] for item in items]
        stock_map = {item["item_name"]: item["current_stock"] for item in items}
        unit_map = {item["item_name"]: item["unit"] for item in items}

        with st.form("stock_out_form"):
            selected_item = st.selectbox("Select Item*", item_names)
            available_stock = stock_map.get(selected_item, 0.0)
            unit_display = unit_map.get(selected_item, "")

            st.info(f"Available Stock: **{available_stock} {unit_display}**")

            quantity = st.number_input(f"Quantity to Dispatch ({unit_display})*", min_value=0.01, max_value=max(0.01, available_stock), value=1.0, step=1.0)
            notes = st.text_input("Notes / Destination", placeholder="e.g., Dispatched to Site A")

            submit = st.form_submit_button("📤 Dispatch Stock", use_container_width=True)

            if submit:
                if quantity > available_stock:
                    st.error("Insufficient stock available!")
                else:
                    try:
                        with get_db() as conn:
                            cursor = conn.cursor()
                            cursor.execute("UPDATE master_items SET current_stock = current_stock - ? WHERE item_name = ?", (quantity, selected_item))
                            cursor.execute("""
                                INSERT INTO transactions (type, item_name, quantity, unit, handled_by, notes)
                                VALUES ('STOCK_OUT', ?, ?, ?, ?, ?)
                            """, (selected_item, quantity, unit_display, user_name, notes))
                            conn.commit()
                            st.success(f"Successfully dispatched {quantity} {unit_display} of **{selected_item}**!")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Error processing stock out: {e}")
    except Exception as e:
        st.error(f"Error loading items: {e}")


def render_schedules(user_name, user_role):
    st.title("🚚 Schedules & Deliveries")
    st.caption("Track incoming material shipments, dispatch schedules, and delivery statuses.")

    tab_overview, tab_add = st.tabs(["📅 Delivery Schedules", "➕ Schedule New Delivery"])

    with tab_overview:
        try:
            with get_db() as conn:
                df = pd.read_sql_query("""
                    SELECT id, item_name, supplier_or_destination, quantity, unit, scheduled_date, status, notes
                    FROM deliveries
                    ORDER BY scheduled_date ASC
                """, conn)

            if not df.empty:
                col_status, col_search = st.columns([1, 2])
                with col_status:
                    status_filter = st.selectbox("Filter Status", ["All", "Pending", "In Transit", "Completed", "Cancelled"])
                with col_search:
                    search_query = st.text_input("🔍 Search Item / Supplier / Destination", placeholder="e.g., Cement, Main Site...")

                filtered_df = df.copy()
                if status_filter != "All":
                    filtered_df = filtered_df[filtered_df["status"] == status_filter]
                if search_query.strip():
                    filtered_df = filtered_df[
                        filtered_df["item_name"].str.contains(search_query.strip(), case=False, na=False) |
                        filtered_df["supplier_or_destination"].str.contains(search_query.strip(), case=False, na=False)
                    ]

                st.divider()

                for idx, row in filtered_df.iterrows():
                    with st.expander(f"📦 {row['item_name']} - {row['scheduled_date']} [{row['status']}]"):
                        c1, c2, c3 = st.columns(3)
                        c1.markdown(f"**Supplier/Destination:** {row['supplier_or_destination']}")
                        c2.markdown(f"**Quantity:** {row['quantity']} {row['unit']}")
                        c3.markdown(f"**Status:** `{row['status']}`")

                        if row["notes"]:
                            st.caption(f"**Notes:** {row['notes']}")

                        new_status = st.selectbox(
                            "Update Status", 
                            ["Pending", "In Transit", "Completed", "Cancelled"], 
                            index=["Pending", "In Transit", "Completed", "Cancelled"].index(row["status"]),
                            key=f"status_select_{row['id']}"
                        )

                        if new_status != row["status"]:
                            if st.button("Save Status Change", key=f"btn_status_{row['id']}"):
                                try:
                                    with get_db() as conn_update:
                                        cursor = conn_update.cursor()
                                        cursor.execute("UPDATE deliveries SET status = ? WHERE id = ?", (new_status, row['id']))
                                        conn_update.commit()
                                        st.success("Status updated successfully!")
                                        st.rerun()
                                except Exception as e:
                                    st.error(f"Error updating delivery status: {e}")
            else:
                st.info("No delivery schedules recorded yet.")
        except Exception as e:
            st.error(f"Error loading delivery schedules: {e}")

    with tab_add:
        with st.form("add_delivery_form"):
            col1, col2 = st.columns(2)
            with col1:
                item_name = st.text_input("Item Name*", placeholder="e.g., Ready-Mix Concrete").strip()
                supplier_dest = st.text_input("Supplier or Destination*", placeholder="e.g., Supplier ABC / Site B").strip()
                scheduled_date = st.date_input("Scheduled Date")
            with col2:
                quantity = st.number_input("Quantity*", min_value=0.01, value=1.0, step=1.0)
                unit = st.text_input("Unit*", placeholder="e.g., bags, cu.m, pcs").strip()
                status = st.selectbox("Initial Status", ["Pending", "In Transit", "Completed"])

            notes = st.text_input("Notes / Special Instructions", placeholder="e.g., Requires forklift unloader")
            submit_btn = st.form_submit_button("📅 Schedule Delivery", use_container_width=True)

            if submit_btn:
                if not item_name or not supplier_dest or not unit:
                    st.error("⚠️ Item Name, Supplier/Destination, and Unit are required.")
                else:
                    try:
                        with get_db() as conn_add:
                            cursor = conn_add.cursor()
                            cursor.execute("""
                                INSERT INTO deliveries (item_name, supplier_or_destination, quantity, unit, scheduled_date, status, notes, created_by)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """, (item_name, supplier_dest, quantity, unit, str(scheduled_date), status, notes, user_name))
                            conn_add.commit()
                            st.success(f"✅ Delivery for **{item_name}** scheduled successfully!")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Failed to create schedule: {e}")

# -------------------------------------------------------------
# MAIN APP / AUTH ROUTER
# -------------------------------------------------------------
if not st.session_state.authenticated:
    st.title("🔐 ARV Inventory Management System")
    st.caption("Please log in to access the system.")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            st.subheader("User Login")
            username = st.text_input("Username").strip()
            password = st.text_input("Password", type="password").strip()
            login_btn = st.form_submit_button("Login", use_container_width=True)

            if login_btn:
                if not username or not password:
                    st.error("⚠️ Please enter both username and password.")
                else:
                    try:
                        with get_db() as conn:
                            cursor = conn.cursor()
                            cursor.execute(
                                "SELECT username, role FROM users WHERE username = ? AND password = ?", 
                                (username, password)
                            )
                            user = cursor.fetchone()
                            
                            if user:
                                st.session_state.authenticated = True
                                st.session_state.user_name = user["username"]
                                st.session_state.user_role = user["role"]
                                st.success("Login successful!")
                                st.rerun()
                            else:
                                st.error("❌ Invalid Username or Password.")
                    except Exception as e:
                        st.error(f"Error during login: {e}")

else:
    # Sidebar
    st.sidebar.title("📦 ARV Inventory")
    st.sidebar.markdown(f"**Logged in as:** `{st.session_state.user_name}`")
    st.sidebar.markdown(f"**Role:** `{st.session_state.user_role}`")
    st.sidebar.divider()

    menu_options = [
        "Manage Items",
        "Stock In",
        "Stock Out",
        "Schedules & Deliveries"
    ]

    page = st.sidebar.radio("Navigation Menu", menu_options)

    st.sidebar.divider()
    if st.sidebar.button("🚪 Logout", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.user_name = ""
        st.session_state.user_role = ""
        st.rerun()

    # Routing
    if page == "Manage Items":
        render_manage_items(st.session_state.user_name, st.session_state.user_role)
    elif page == "Stock In":
        render_stock_in(st.session_state.user_name, st.session_state.user_role)
    elif page == "Stock Out":
        render_stock_out(st.session_state.user_name, st.session_state.user_role)
    elif page == "Schedules & Deliveries":
        render_schedules(st.session_state.user_name, st.session_state.user_role)
