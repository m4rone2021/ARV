# ARV — Construction Site Inventory System

A business inventory management system for construction sites, built with Streamlit and backed by Supabase (Postgres).

---

## Overview

ARV tracks construction-site material inventory: receiving, issuing, dispatching, and physical counts. It supports role-based access (Admin / User), audit logging, low-stock alerts, and delivery scheduling.

Originally built on SQLite with Google Drive backups, ARV now runs entirely on Supabase for real-time multi-user access and cloud durability.

---

## Features

| Feature | Description |
|---|---|
| Executive Dashboard | Real-time KPIs, pending dispatches, low-stock alerts, active tasks |
| Master Item Catalog | Full CRUD on the item catalog with categories, units, thresholds |
| Stock IN | Record material receipts with optional attachment (Drive upload) |
| Stock OUT | Issue materials with atomic stock guards (via Postgres RPC) |
| Low Stock Alerts | Threshold monitoring + one-click restock scheduling |
| Physical Inventory | Count entry, variance tracking, admin approval workflow |
| Schedules & Deliveries | Multi-item dispatch batches with reserved-stock tracking |
| Reminders & Tasks | Per-user task lists with priority and due-date tracking |
| Transaction Ledger | Unified audit log across stock, delivery, physical, and user events |
| Edit / Void | Correct mistakes with automatic stock reversal |
| User Management | Admin-only user CRUD with bcrypt password hashing |

---

## Architecture

    Streamlit UI (app.py + views/*.py)
            |
            v
    database.py  (Supabase SDK)
      - Auth: bcrypt
      - Reads/writes: PostgREST
      - Atomic stock: Postgres RPC
            |
            v
    Supabase (Postgres)
      9 tables - 6 enums - 2 views - 2 RPCs
      Row-Level Security enabled

---

## Getting Started

### Prerequisites

- Python 3.11+
- A Supabase project (free tier works)
- (Optional) Google service account for attachment uploads

### Installation

    git clone https://github.com/m4rone2021/ARV.git
    cd ARV
    python -m pip install -r requirements.txt

### Configure secrets

Create .streamlit/secrets.toml with:

    [supabase]
    url = "https://your-project.supabase.co"
    anon_key = "sb_publishable_..."
    service_role_key = "sb_secret_..."

    [google_drive]
    folder_id = "your-drive-folder-id"

Never commit secrets.toml — it is in .gitignore.

### Initialize the database

Run the SQL from supabase/schema.sql in your Supabase project's SQL editor.

### Run the app

    streamlit run app.py

Open http://localhost:8501.

---

## Default Credentials

After schema setup and migration, the initial admin is:

- Username: admin
- Password: see your migration log or the migration_meta table

Change this immediately after first login.

---

## Project Structure

    ARV/
      app.py                  Entry point, navigation, login
      database.py             Supabase data layer
      verify_db.py            Connectivity check
      requirements.txt
      .streamlit/
        secrets.toml          (gitignored)
      components/
        dispatch_card.py      Reusable dispatch batch UI
      views/
        dashboard.py
        stock_in.py
        stock_out.py
        manage_items.py
        low_stock.py
        physical_inventory.py
        schedules.py
        reminders.py
        audit_log.py
        edit_void.py
        user_management.py
      supabase/
        schema.sql            Full Postgres schema
      _migration/             SQLite to Supabase migration (gitignored)

---

## Security

- Passwords: bcrypt, 12 rounds
- Row-Level Security: enabled on all tables, deny-all for anon
- Service-role key: server-side only, never exposed to clients
- Secrets: managed in .streamlit/secrets.toml (gitignored)

---

## License

Private - all rights reserved.
