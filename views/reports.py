import re
from datetime import datetime, timedelta, date

import pandas as pd
import streamlit as st

from database import sb
from utils.report_builder import build_excel_report, build_pdf_report


REPORT_TYPES = [
    "Full Inventory Report",
    "Inventory Snapshot",
    "Movement Report (IN/OUT)",
    "Project Consumption",
    "Supplier Receipts",
    "Low Stock and Alerts",
    "Physical Count Report",
]

PERIODS = ["Daily (Today)", "Weekly (Last 7 days)", "Monthly (Last 30 days)", "Custom Range"]


def _fetch_transactions(start, end):
    try:
        res = (
            sb()
            .table("transactions")
            .select("id, timestamp, type, item_name, quantity, unit, handled_by, notes, project_name")
            .gte("timestamp", start.isoformat())
            .lte("timestamp", end.isoformat() + "T23:59:59")
            .order("timestamp", desc=True)
            .execute()
        )
        return pd.DataFrame(res.data or [])
    except Exception as e:
        st.warning("Could not fetch transactions: " + str(e))
        return pd.DataFrame()


def _fetch_master_items():
    try:
        res = (
            sb()
            .table("master_items")
            .select("item_name, category, unit, current_stock, reserved_stock, min_threshold")
            .order("item_name")
            .execute()
        )
        return pd.DataFrame(res.data or [])
    except Exception as e:
        st.warning("Could not fetch master items: " + str(e))
        return pd.DataFrame()


def _fetch_deliveries(start, end):
    try:
        res = (
            sb()
            .table("deliveries")
            .select("id, created_at, dispatch_id, item_name, expected_quantity, unit, status, destination, project, requested_by, driver_name")
            .gte("created_at", start.isoformat())
            .lte("created_at", end.isoformat() + "T23:59:59")
            .order("created_at", desc=True)
            .execute()
        )
        return pd.DataFrame(res.data or [])
    except Exception as e:
        return pd.DataFrame()


def _period_bounds(period_choice, custom_start, custom_end):
    today = date.today()
    if period_choice == "Daily (Today)":
        return today, today, "Daily Report - " + today.strftime("%B %d, %Y")
    if period_choice == "Weekly (Last 7 days)":
        start = today - timedelta(days=6)
        return start, today, "Weekly Report - " + start.strftime("%b %d") + " to " + today.strftime("%b %d, %Y")
    if period_choice == "Monthly (Last 30 days)":
        # Monthly = 1st of current month to today (not rolling 30 days)
        start = today.replace(day=1)
        return start, today, "Monthly Report - " + start.strftime("%b %d") + " to " + today.strftime("%b %d, %Y")
    return custom_start, custom_end, "Custom - " + custom_start.strftime("%b %d, %Y") + " to " + custom_end.strftime("%b %d, %Y")




def _fetch_deliveries_all():
    try:
        res = (
            sb()
            .table("deliveries")
            .select("id, dispatch_id, item_name, expected_quantity, unit, "
                    "expected_date, scheduled_date, status, destination, project, "
                    "driver_name, created_at")
            .order("expected_date", desc=True)
            .limit(500)
            .execute()
        )
        return res.data or []
    except Exception:
        return []


def _fetch_discrepancies():
    try:
        res = (
            sb()
            .table("discrepancies")
            .select("id, timestamp, item_name, system_stock, physical_count, "
                    "variance, unit, submitted_by, status")
            .order("timestamp", desc=True)
            .limit(200)
            .execute()
        )
        return res.data or []
    except Exception:
        return []




def _build_download_filename(report_type, period_choice, ext):
    """Build a descriptive download filename including the reporting period."""
    today = datetime.now().strftime("%Y-%m-%d")
    safe_type = report_type.replace(" ", "_").replace("(", "").replace(")", "").replace("/", "-")

    # Slug for the period
    if "Daily" in period_choice:
        period_slug = "Daily_" + today
    elif "Weekly" in period_choice:
        period_slug = "Weekly_" + today
    elif "Monthly" in period_choice:
        period_slug = "Monthly_" + today
    elif "Custom" in period_choice:
        period_slug = "Custom_" + today
    else:
        period_slug = today

    return "ARV_" + safe_type + "_" + period_slug + "." + ext


def render_reports(user_name, user_role):
    st.title("Reports")
    st.caption("Generate downloadable business reports for inventory activity.")

    with st.container(border=True):
        c1, c2 = st.columns(2)
        with c1:
            report_type = st.selectbox("Report Type", REPORT_TYPES)
        with c2:
            period_choice = st.selectbox("Period", PERIODS)

        custom_start = custom_end = None
        if period_choice == "Custom Range":
            cc1, cc2 = st.columns(2)
            with cc1:
                custom_start = st.date_input("Start Date", value=date.today() - timedelta(days=30))
            with cc2:
                custom_end = st.date_input("End Date", value=date.today())

        start, end, period_label = _period_bounds(period_choice, custom_start, custom_end)
        st.caption("Period: " + period_label)

    if st.button("Generate Report Preview", type="primary"):
        st.session_state["report_generated"] = True
        st.session_state["report_type"] = report_type
        st.session_state["period_label"] = period_label
        st.session_state["start"] = start.isoformat()
        st.session_state["end"] = end.isoformat()

    if not st.session_state.get("report_generated"):
        st.info("Pick a report type and period, then click Generate Report Preview.")
        return

    report_type = st.session_state["report_type"]
    period_label = st.session_state["period_label"]
    start = date.fromisoformat(st.session_state["start"])
    end = date.fromisoformat(st.session_state["end"])

    with st.spinner("Building report data..."):
        tx_df = _fetch_transactions(start, end)
        items_df = _fetch_master_items()
        deliv_df = _fetch_deliveries(start, end)

    summary = {}
    details = []
    by_item = []

    snapshot_types = ("Inventory Snapshot", "Full Inventory Report", "Low Stock and Alerts")
    tx_types = ("Movement Report (IN/OUT)", "Project Consumption", "Supplier Receipts")

    # ---- SNAPSHOT: build by_item from master_items ----
    if report_type in snapshot_types:
        if not items_df.empty:
            items_df["current_stock"] = items_df["current_stock"].fillna(0)
            items_df["reserved_stock"] = items_df["reserved_stock"].fillna(0)
            items_df["available"] = items_df["current_stock"] - items_df["reserved_stock"]
            items_df["status"] = items_df.apply(
                lambda r: "OUT" if r["available"] <= 0
                else ("LOW" if r["available"] <= r["min_threshold"] else "OK"),
                axis=1,
            )
            summary["Total Items"] = len(items_df)
            summary["In Stock"] = int((items_df["status"] == "OK").sum())
            summary["Low Stock"] = int((items_df["status"] == "LOW").sum())
            summary["Out of Stock"] = int((items_df["status"] == "OUT").sum())
            summary["Total Units On-Hand"] = round(float(items_df["current_stock"].sum()), 2)

            snap = items_df[[
                "item_name", "category", "unit", "current_stock",
                "reserved_stock", "available", "min_threshold", "status",
            ]].copy()
            snap.columns = ["Item", "Category", "Unit", "On-Hand",
                            "Reserved", "Available", "Min", "Status"]
            by_item = snap.to_dict(orient="records")

    # ---- TRANSACTIONS: build by_item from transaction summary ----
    elif report_type in tx_types:
        if not tx_df.empty:
            tx_df["type"] = tx_df["type"].apply(
                lambda t: "IN" if t == "IN" else ("OUT" if t == "OUT" else t)
            )

            if report_type == "Supplier Receipts":
                tx_df = tx_df[tx_df["type"] == "IN"]
                summary["Report Scope"] = "Stock IN receipts only"
            elif report_type == "Project Consumption":
                tx_df = tx_df[tx_df["type"] == "OUT"]
                summary["Report Scope"] = "Stock OUT issues only"
            elif report_type == "Movement Report (IN/OUT)":
                summary["Report Scope"] = "All IN and OUT activity"

            if tx_df.empty:
                st.warning("No matching transactions for this report type and period.")
                return

            in_df = tx_df[tx_df["type"] == "IN"]
            out_df = tx_df[tx_df["type"] == "OUT"]
            summary["Total Transactions"] = len(tx_df)
            summary["Stock IN Lines"] = len(in_df)
            summary["Stock OUT Lines"] = len(out_df)
            summary["Stock IN Qty"] = round(float(in_df["quantity"].fillna(0).sum()), 2) if not in_df.empty else 0
            summary["Stock OUT Qty"] = round(float(out_df["quantity"].fillna(0).sum()), 2) if not out_df.empty else 0

            # Summary by item — grouped transaction view
            grouped = (
                tx_df.groupby(["item_name", "unit", "type"])["quantity"]
                .sum()
                .reset_index()
            )
            by_item = [
                {
                    "Item": r["item_name"],
                    "Unit": r["unit"],
                    "Type": r["type"],
                    "Total Qty": round(float(r["quantity"]), 2),
                }
                for _, r in grouped.iterrows()
            ]

    # ---- PHYSICAL COUNT ----
    elif report_type == "Physical Count Report":
        # by_item stays empty; discrepancies are shown in extras
        summary["Physical Counts"] = len(details or [])

    # ---

    st.divider()
    st.subheader("Executive Summary")
    if summary:
        cols = st.columns(min(len(summary), 4))
        for i, (k, v) in enumerate(summary.items()):
            cols[i % len(cols)].metric(str(k), str(v))
    else:
        st.info("No data in this period.")

    if by_item:
        st.subheader("Summary by Item")
        st.dataframe(pd.DataFrame(by_item), width='stretch', hide_index=True)

    if details:
        st.subheader("Detailed Log (first 50)")
        st.dataframe(pd.DataFrame(details).head(50), width='stretch', hide_index=True)

    st.divider()
    st.subheader("Download")

    # Paper size selector (PDF only)
    ps1, ps2 = st.columns([1, 2])
    with ps1:
        _paper_choice = st.selectbox(
            "Paper size (PDF)",
            ["Standard (Letter)", "Long (Legal)"],
            key="report_paper_size_sel",
        )
    _paper_key = "legal" if "Legal" in _paper_choice else "letter"

    c1, c2 = st.columns(2)

    with c1:
        if st.button("Generate PDF", type="primary", width='stretch'):
            with st.spinner("Building PDF..."):
                extras = {}
                if "Full" in report_type or "Deliver" in report_type:
                    extras["deliveries"] = _fetch_deliveries_all()
                if "Full" in report_type or "Physical" in report_type or "Snapshot" in report_type:
                    extras["discrepancies"] = _fetch_discrepancies()
                pdf = build_pdf_report(
                    report_type, period_label, {}, summary, details,
                    by_item, user_name, paper_size=_paper_key, extras=extras,
                )
            st.download_button(
                "Download PDF",
                data=pdf,
                file_name=_build_download_filename(report_type, period_choice, "pdf"),
                mime="application/pdf",
                width='stretch',
            )

    # Admin-only: editable PDF
    if user_role == "Admin":
        with st.expander("Advanced (admin only) — editable PDF"):
            st.caption(
                "This version has selectable text and editable tables. "
                "For internal use only. Do not distribute externally."
            )
            if st.button("Generate editable PDF", width='stretch'):
                with st.spinner("Building editable PDF..."):
                    try:
                        from utils.report_builder import build_pdf_report_editable
                        pdf_editable = build_pdf_report_editable(
                            report_type, period_label, {}, summary, details,
                            by_item, user_name, paper_size=_paper_key,
                        )
                        st.download_button(
                            "Download editable PDF",
                            data=pdf_editable,
                            file_name=_build_download_filename(report_type, period_choice, "pdf").replace(".pdf", "_EDITABLE.pdf"),
                            mime="application/pdf",
                            width='stretch',
                        )
                    except Exception as e:
                        st.error(f"Editable PDF failed: {e}")

    with c2:
        if st.button("Generate Excel", width='stretch'):
            with st.spinner("Building Excel..."):
                xlsx = build_excel_report(report_type, period_label, {}, summary, details, by_item)
            st.download_button(
                "Download Excel",
                data=xlsx,
                file_name=_build_download_filename(report_type, period_choice, "xlsx"),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width='stretch',
            )
