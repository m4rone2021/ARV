"""
ARV database.py  —  Supabase (Postgres) data layer.

Replaces the SQLite implementation. Public API is preserved so views
continue importing the same names, but all data now lives in Supabase.

Critical stock movements call Postgres RPC functions for atomicity.
Google Drive is kept ONLY for file attachments (not DB backups).
"""

import hashlib  # noqa: F401  (kept for reference, not used for passwords)
import io
import os
from datetime import datetime
from pathlib import Path

import bcrypt
import pandas as pd
import streamlit as st

# -----------------------------------------------------------------------------
# EXPORTED MODULE API  (kept identical to the SQLite version)
# -----------------------------------------------------------------------------
__all__ = [
    "init_db",
    "login_user",
    "hash_password",
    "verify_password",
    "backup_db_to_gdrive",
    "upload_file_to_gdrive",
    "get_drive_service",
    "create_test_file_in_gdrive",
    "get_db",
    "register_item",
    "add_stock_transaction",
    "resolve_discrepancy",
    "update_dispatch_status",
    "add_scheduled_delivery",
    "save_dispatch_batch",
    "sb",
    "DB_FILE",
    "UPLOAD_DIR",
]


# -----------------------------------------------------------------------------
# SUPABASE CLIENT  (cached across Streamlit reruns)
# -----------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def _sb_client():
    """Create and cache the Supabase client. Runs once per session."""
    try:
        from supabase import create_client
    except ImportError:
        raise ImportError(
            "Missing 'supabase' package. Run: python -m pip install supabase"
        )

    cfg = st.secrets.get("supabase", {})
    url = cfg.get("url")
    key = cfg.get("service_role_key")
    if not url or not key:
        raise RuntimeError(
            "Missing [supabase] url / service_role_key in .streamlit/secrets.toml"
        )
    return create_client(url, key)


def sb():
    """Return the cached Supabase client."""
    return _sb_client()


# -----------------------------------------------------------------------------
# PATHS  (legacy shims — kept so old imports don't break)
# -----------------------------------------------------------------------------
LOCAL_WIN_DIR = Path(r"D:\Inventory System Files")
if LOCAL_WIN_DIR.exists():
    DATA_DIR = LOCAL_WIN_DIR
else:
    DATA_DIR = Path("./data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_FILE = DATA_DIR / "inventory.db"        # no longer used — kept for compat
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# -----------------------------------------------------------------------------
# PASSWORD HASHING  (bcrypt)
# -----------------------------------------------------------------------------
def hash_password(password: str) -> str:
    """Return a bcrypt hash for the given password."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode(
        "utf-8"
    )


def verify_password(password: str, password_hash: str) -> bool:
    """Check a plaintext password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"), password_hash.encode("utf-8")
        )
    except Exception:
        return False


# -----------------------------------------------------------------------------
# AUTH
# -----------------------------------------------------------------------------
def login_user(username: str, password: str):
    """Authenticate a user. Returns dict with username/role, or None."""
    try:
        res = (
            sb()
            .table("users")
            .select("username, role, password_hash, is_active")
            .eq("username", username.strip())
            .limit(1)
            .execute()
        )
    except Exception as e:
        print(f"[login_user] Supabase error: {e}")
        return None

    rows = res.data or []
    if not rows:
        return None

    user = rows[0]
    if not user.get("is_active", True):
        return None

    if not verify_password(password, user["password_hash"]):
        return None

    # Update last_login_at (best effort)
    try:
        sb().table("users").update(
            {"last_login_at": datetime.utcnow().isoformat()}
        ).eq("username", user["username"]).execute()
    except Exception:
        pass

    return {"username": user["username"], "role": user["role"]}


# -----------------------------------------------------------------------------
# LEGACY SHIMS
# -----------------------------------------------------------------------------
def init_db():
    """No-op: schema already lives in Supabase."""
    return None


def backup_db_to_gdrive():
    """No-op stub. Kept so old call sites don't crash.

    Supabase has built-in backups; we no longer ship the SQLite file to Drive.
    """
    return None


def get_db():
    """Legacy SQLite context manager.

    Any view still using `with get_db() as conn:` needs to be refactored to
    use the Supabase client. Raise a clear error to make that obvious.
    """
    raise RuntimeError(
        "get_db() has been retired. This view still uses raw SQLite.\n"
        "Refactor it to use: from database import sb\n"
        "Then: sb().table('...').select('...').execute()"
    )


# -----------------------------------------------------------------------------
# INVENTORY WRITES
# -----------------------------------------------------------------------------
def register_item(
    item_name: str,
    category: str,
    unit: str,
    initial_stock: float = 0.0,
    min_threshold: float = 10.0,
    remarks: str = "",
):
    """Register a new item in master_items."""
    sb().table("master_items").insert(
        {
            "item_name": item_name,
            "category": category,
            "unit": unit,
            "current_stock": float(initial_stock),
            "reserved_stock": 0.0,
            "min_threshold": float(min_threshold),
            "remarks": remarks,
        }
    ).execute()


def add_stock_transaction(
    trans_type: str,
    item_name: str,
    quantity: float,
    unit: str,
    handled_by: str,
    notes: str = "",
    project_name: str | None = None,
):
    """Execute a stock transaction via the atomic RPC.

    trans_type must be one of: IN, OUT, ADJUSTMENT, RECONCILIATION
    """
    trans_type = trans_type.upper().strip()
    if trans_type not in ("IN", "OUT", "ADJUSTMENT", "RECONCILIATION"):
        raise ValueError(
            "trans_type must be IN, OUT, ADJUSTMENT, or RECONCILIATION"
        )

    res = sb().rpc(
        "record_stock_transaction",
        {
            "p_type": trans_type,
            "p_item_name": item_name,
            "p_quantity": float(quantity),
            "p_unit": unit,
            "p_handled_by": handled_by,
            "p_notes": notes or None,
            "p_project_name": project_name,
        },
    ).execute()

    return res.data


# -----------------------------------------------------------------------------
# DELIVERIES
# -----------------------------------------------------------------------------
def add_scheduled_delivery(
    due_date: str,
    project: str,
    item_description: str,
    qty: float,
    requestor: str,
    created_by: str,
    supplier: str | None = None,
    unit: str = "pcs",
):
    """Insert a single scheduled delivery row."""
    sb().table("deliveries").insert(
        {
            "expected_date": due_date,
            "scheduled_date": due_date,
            "project": project,
            "item_name": item_description,
            "expected_quantity": float(qty),
            "unit": unit,
            "requested_by": requestor,
            "created_by": created_by,
            "supplier": supplier,
            "status": "Pending",
        }
    ).execute()


def save_dispatch_batch(
    dispatch_header: dict, delivery_cart: list, created_by: str | None = None
):
    """Insert a batch of dispatch items and reserve the corresponding stock."""
    creator = (
        created_by
        or dispatch_header.get("created_by")
        or (st.session_state.get("user_name") if hasattr(st, "session_state") else None)
        or "System"
    )

    rows = []
    for item in delivery_cart:
        rows.append(
            {
                "dispatch_id": dispatch_header["dispatch_id"],
                "item_name": item["item_name"],
                "unit": item.get("unit", "pcs"),
                "expected_quantity": float(item["quantity"]),
                "expected_date": dispatch_header["scheduled_date"],
                "scheduled_date": dispatch_header["scheduled_date"],
                "destination": dispatch_header["destination"],
                "requested_by": dispatch_header["requested_by"],
                "created_by": creator,
                "project": dispatch_header["project"],
                "status": "Pending",
                "is_priority": bool(dispatch_header.get("is_priority", 0)),
                "driver_name": dispatch_header.get("driver_name", ""),
                "notes": item.get("notes", ""),
            }
        )

    if rows:
        sb().table("deliveries").insert(rows).execute()

    # Reserve stock for each unique item
    by_item: dict[str, float] = {}
    for item in delivery_cart:
        by_item[item["item_name"]] = by_item.get(item["item_name"], 0.0) + float(
            item["quantity"]
        )

    for item_name, qty in by_item.items():
        cur = (
            sb()
            .table("master_items")
            .select("reserved_stock")
            .eq("item_name", item_name)
            .limit(1)
            .execute()
        )
        if cur.data:
            new_reserved = float(cur.data[0].get("reserved_stock") or 0.0) + qty
            sb().table("master_items").update(
                {"reserved_stock": new_reserved}
            ).eq("item_name", item_name).execute()


def update_dispatch_status(
    dispatch_id: str,
    new_status: str,
    handled_by: str = "System",
    driver_name: str | None = None,
    delivery_notes: str | None = None,
):
    """Update the status of all rows in a dispatch batch.

    - Cancelled  → releases reserved_stock
    - Completed  → deducts current_stock, releases reserved_stock, logs OUT tx
    """
    new_status_clean = new_status.strip()
    if new_status_clean not in ("Pending", "In Transit", "Completed", "Cancelled"):
        raise ValueError("Invalid status provided.")

    rows = (
        sb()
        .table("deliveries")
        .select("item_name, expected_quantity, unit, status")
        .eq("dispatch_id", dispatch_id)
        .execute()
        .data
        or []
    )
    if not rows:
        raise ValueError(f"No dispatch records found for ID '{dispatch_id}'.")

    current_status = rows[0]["status"]
    if current_status in ("Completed", "Cancelled"):
        raise ValueError(f"Dispatch '{dispatch_id}' is already {current_status}.")

    for item in rows:
        item_name = item["item_name"]
        qty = float(item["expected_quantity"])
        unit = item["unit"]

        cur = (
            sb()
            .table("master_items")
            .select("current_stock, reserved_stock")
            .eq("item_name", item_name)
            .limit(1)
            .execute()
        )
        if not cur.data:
            continue
        stock = cur.data[0]
        current_stock = float(stock.get("current_stock") or 0.0)
        reserved_stock = float(stock.get("reserved_stock") or 0.0)

        if new_status_clean == "Cancelled":
            new_reserved = max(0.0, reserved_stock - qty)
            sb().table("master_items").update(
                {"reserved_stock": new_reserved}
            ).eq("item_name", item_name).execute()

        elif new_status_clean == "Completed":
            new_stock = max(0.0, current_stock - qty)
            new_reserved = max(0.0, reserved_stock - qty)
            sb().table("master_items").update(
                {"current_stock": new_stock, "reserved_stock": new_reserved}
            ).eq("item_name", item_name).execute()

            sb().table("transactions").insert(
                {
                    "type": "OUT",
                    "item_name": item_name,
                    "quantity": qty,
                    "unit": unit,
                    "handled_by": handled_by,
                    "notes": f"Completed Dispatch #{dispatch_id}",
                }
            ).execute()

    update_payload = {"status": new_status_clean}
    if driver_name is not None:
        update_payload["driver_name"] = driver_name
    if delivery_notes:
        update_payload["notes"] = delivery_notes

    sb().table("deliveries").update(update_payload).eq(
        "dispatch_id", dispatch_id
    ).execute()


# -----------------------------------------------------------------------------
# DISCREPANCIES
# -----------------------------------------------------------------------------
def resolve_discrepancy(
    discrepancy_id: str,
    resolved_by: str,
    resolution_notes: str,
    approve_adjustment: bool = True,
):
    """Approve or reject a discrepancy. If approved, set master_items stock."""
    disc = (
        sb()
        .table("discrepancies")
        .select("*")
        .eq("id", discrepancy_id)
        .limit(1)
        .execute()
        .data
    )
    if not disc:
        raise ValueError(f"Discrepancy record {discrepancy_id} not found.")
    d = disc[0]

    status = "APPROVED" if approve_adjustment else "REJECTED"
    sb().table("discrepancies").update(
        {
            "status": status,
            "resolved_by": resolved_by,
            "resolved_timestamp": datetime.utcnow().isoformat(),
            "resolution_notes": resolution_notes,
        }
    ).eq("id", discrepancy_id).execute()

    if approve_adjustment:
        sb().table("master_items").update(
            {"current_stock": float(d["physical_count"])}
        ).eq("item_name", d["item_name"]).execute()

        sb().table("transactions").insert(
            {
                "type": "RECONCILIATION",
                "item_name": d["item_name"],
                "quantity": float(d["physical_count"]),
                "unit": d["unit"],
                "handled_by": resolved_by,
                "notes": f"Discrepancy Audit #{discrepancy_id}: {resolution_notes}",
            }
        ).execute()


# -----------------------------------------------------------------------------
# GOOGLE DRIVE  (attachments only — no more DB backups)
# -----------------------------------------------------------------------------
def clean_private_key(key_str: str) -> str:
    if not key_str:
        return key_str
    key_str = key_str.strip("'\" ")
    if "\\n" in key_str:
        key_str = key_str.replace("\\n", "\n")
    if (
        "-----BEGIN PRIVATE KEY-----" in key_str
        and not key_str.startswith("-----BEGIN PRIVATE KEY-----")
    ):
        key_str = (
            "-----BEGIN PRIVATE KEY-----"
            + key_str.split("-----BEGIN PRIVATE KEY-----")[-1]
        )
    return key_str.strip()


def get_drive_service():
    """Authenticate and build Google Drive API service (attachments only)."""
    SCOPES = ["https://www.googleapis.com/auth/drive"]

    # 1. Service account via Streamlit secrets
    if hasattr(st, "secrets") and "gcp_service_account" in st.secrets:
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            creds_dict = dict(st.secrets["gcp_service_account"])
            if "private_key" in creds_dict:
                creds_dict["private_key"] = clean_private_key(
                    creds_dict["private_key"]
                )
            creds = service_account.Credentials.from_service_account_info(
                creds_dict, scopes=SCOPES
            )
            return build("drive", "v3", credentials=creds), "Service Account"
        except Exception as e:
            print(f"[Drive Warning] Service Account auth failed: {e}")

    # 2. OAuth refresh token
    if hasattr(st, "secrets") and "gdrive_token" in st.secrets:
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            token_info = dict(st.secrets["gdrive_token"])
            creds = Credentials.from_authorized_user_info(token_info, SCOPES)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            return build("drive", "v3", credentials=creds), "OAuth Token"
        except Exception as e:
            print(f"[Drive Warning] OAuth Token auth failed: {e}")

    # 3. Local token.json / credentials.json
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        creds = None
        if os.path.exists("token.json"):
            try:
                creds = Credentials.from_authorized_user_file(
                    "token.json", SCOPES
                )
            except Exception as e:
                print(f"[Drive Warning] Invalid token.json deleted: {e}")
                os.remove("token.json")

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            elif os.path.exists("credentials.json"):
                flow = InstalledAppFlow.from_client_secrets_file(
                    "credentials.json", SCOPES
                )
                creds = flow.run_local_server(port=0)
                with open("token.json", "w") as token:
                    token.write(creds.to_json())
            else:
                print("[Drive Warning] No valid credentials found.")
                return None, None

        return build("drive", "v3", credentials=creds), "Local Credentials"
    except Exception as e:
        print(f"[Drive Auth Error] {e}")
        return None, None


def upload_file_to_gdrive(
    file_bytes: bytes,
    file_name: str,
    mime_type: str = "application/octet-stream",
) -> str | None:
    """Upload raw bytes to Google Drive and return the shareable link."""
    service, auth_type = get_drive_service()
    if not service:
        print("[Drive Upload Error] Could not initialize Drive service.")
        return None

    try:
        from googleapiclient.http import MediaIoBaseUpload

        folder_id = None
        if hasattr(st, "secrets"):
            folder_id = st.secrets.get("google_drive", {}).get("folder_id")

        file_metadata = {"name": file_name}
        if folder_id:
            file_metadata["parents"] = [folder_id]

        media = MediaIoBaseUpload(
            io.BytesIO(file_bytes), mimetype=mime_type, resumable=True
        )

        file = (
            service.files()
            .create(
                body=file_metadata,
                media_body=media,
                fields="id, webViewLink",
                supportsAllDrives=True,
            )
            .execute()
        )
        return file.get("webViewLink")
    except Exception as e:
        print(f"[Drive Upload Error] Failed to upload '{file_name}': {e}")
        return None


def create_test_file_in_gdrive():
    """Sanity-check upload to Drive."""
    content = (
        "ARV test file - if you can read this, Drive auth works.\n"
        f"Timestamp: {datetime.utcnow().isoformat()}\n"
    )
    return upload_file_to_gdrive(
        content.encode("utf-8"), "ARV_drive_test.txt", "text/plain"
    )
