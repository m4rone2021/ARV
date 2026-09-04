# views/stock_in.py
import os
import sqlite3
import pandas as pd
import streamlit as st
from database import get_db, init_db

# Fallback for UPLOAD_DIR if not exported
try:
    from database import UPLOAD_DIR
except ImportError:
    UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")
    os.makedirs(UPLOAD_DIR, exist_ok=True)

def render_stock_in(user_name, user_role):
    st.title("📥 Stock IN Receive Log")
    st.caption("Record site material receipts, deliveries, and stock replenishment.")

    # Ensure database schema exists
    init_db()

    # Load master items to stock in
    try:
        with get_db() as conn:
            items_df = pd.read_sql_query("SELECT item_name, category, unit, current_stock FROM master_items ORDER BY item_name ASC", conn)
    except Exception as e:
        st.error(f"Failed to fetch master items: {e}")
        return

    if items_df.empty:
        st.warning("⚠️ No master items found in the database. Please add items in **Manage Master Items** first.")
        return

    with st.form("stock_in_form", clear_on_submit=True):
        col1, col2 = st.columns(2)

        with col1:
            selected_item = st.selectbox("Select Master Item*", items_df["item_name"].tolist())
            
            # Fetch details for the selected item
            item_info = items_df[items_df["item_name"] == selected_item].iloc[0]
            current_stock = item_info["current_stock"]
            unit = item_info["unit"]
            category = item_info["category"]

            st.info(f"Category: **{category}** | Current Balance: **{current_stock} {unit}**")

            quantity = st.number_input(f"Received Quantity ({unit})*", min_value=0.1, value=1.0, step=1.0)

        with col2:
            supplier_source = st.text_input("Supplier / Source / DR No.*", placeholder="e.g., ABC Hardware, DR #10293")
            remarks = st.text_input("Remarks / Notes", placeholder="e.g., Batch code, Storage bay A-3")
            uploaded_file = st.file_uploader("Attach Delivery Receipt / Invoice (Optional)", type=["png", "jpg", "jpeg", "pdf"])

        submit_btn = st.form_submit_button("📥 Log Stock IN Receipt", use_container_width=True)

        if submit_btn:
            if not supplier_source.strip():
                st.error("⚠️ 'Supplier / Source / DR No.' is required.")
            else:
                attachment_path = None
                
                # Handle File Upload
                if uploaded_file is not None:
                    file_filename = f"IN_{selected_item.replace(' ', '_')}_{uploaded_file.name}"
                    save_path = os.path.join(UPLOAD_DIR, file_filename)
                    with open(save_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    attachment_path = file_filename

                try:
                    new_stock = current_stock + quantity
                    
                    # Combine supplier, remarks, and attachment info into the single 'notes' column
                    notes_list = [f"Supplier/DR: {supplier_source.strip()}"]
                    if remarks.strip():
                        notes_list.append(f"Remarks: {remarks.strip()}")
                    if attachment_path:
                        notes_list.append(f"Attachment: {attachment_path}")
                    
                    full_notes = " | ".join(notes_list)

                    with get_db() as conn:
                        cursor = conn.cursor()
                        # Update master stock limit
                        cursor.execute("UPDATE master_items SET current_stock = ? WHERE item_name = ?", (new_stock, selected_item))
                        
                        # Log IN transaction entry matching the transactions schema
                        cursor.execute("""
                            INSERT INTO transactions (type, item_name, quantity, unit, handled_by, notes)
                            VALUES ('STOCK IN', ?, ?, ?, ?, ?)
                        """, (selected_item, quantity, unit, user_name, full_notes))
                        
                        conn.commit()

                    st.success(f"✅ Added {quantity} {unit} to '{selected_item}'. New stock level: {new_stock} {unit}.")
                    st.rerun()
                
                except Exception as e:
                    st.error(f"Error executing database stock increment: {e}")
