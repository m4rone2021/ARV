# SNAPSHOT_v15.4.md

> **ARV - Water System Domain Shipped**
> Date: 2026-10-08
> Baseline: SNAPSHOT_v15.3.md
> Status: **FROZEN**

---

## 1. What Shipped Since v15.3

| Item | Status |
|---|---|
| Water domain module (9 files under `watersystem/`) | OK |
| `master_items` extended with 8 water-specific columns | OK |
| `lookup_options` table with approval workflow | OK |
| 31 seeded lookup options (7 categories, 10 materials, 14 sizes) | OK |
| Water item CRUD with pricing | OK |
| Drive image upload for water items | OK |
| Pending lookups admin approval screen | OK |
| `app.py` dispatches to `watersystem.views.render` | OK |
| Google Drive OAuth working local + deployed | OK |

---## 2. Repo State

| Item | Value |
|---|---|
| HEAD commit | 4c50b92 |
| Branch | main (tracking origin/main) |
| Remote | https://github.com/m4rone2021/ARV.git |
| Live URL | https://arvinventory.streamlit.app |
| Supabase project | dirgeqpjpisfiawxihqw |

### Commit timeline (this arc)
- d794572 feat: login_user returns access flags
- c34132c feat: app.py domain switcher + access-flag routing
- d204daa docs: SNAPSHOT_v15.2 - multi-domain access foundation
- d0bdf10 feat(user_mgmt): three access checkboxes + password-confirmed delete
- aadd050 docs: SNAPSHOT_v15.3 - user management + access model complete
- 4c50b92 feat(watersystem): water domain module + manage items screen

---

## 3. Water Domain Module

```
watersystem/
  __init__.py
  config.py
  lookups.py
  items.py
  views.py
  screens/
    __init__.py
    manage_items.py
    pending_lookups.py
    drive_upload.py
```

All queries filter by warehouse='watersystem'.

---
## 4. Schema Changes

### master_items (extended)

Eight new nullable columns: material, size, cost_php, shipping_php, total_cost_php, markup_pct, selling_price_php, image_url.

### lookup_options (new table)

Columns: id, kind (category/material/size), value, warehouse, status (pending/approved/rejected), created_at, created_by, approved_at, approved_by, rejection_reason.

Seeded 31 options: 7 categories, 10 materials, 14 sizes, all approved, created_by='system'.

---

## 5. Pricing Model

```
total_cost    = cost_php + shipping_php
selling_price = manual_price                    if manual provided
              = total_cost * (1 + markup/100)   if markup provided
              = total_cost                      otherwise
```

---
## 6. Lookup Approval Workflow

Users request new options -> status=pending. Admins approve -> status=approved. Admins reject with reason -> status=rejected. Admins creating new values get immediate approved status.

Pending count shown as sidebar badge for admins only.

---

## 7. Drive Image Upload

Local + deployed read [gdrive_token] and [google_drive] folder_id from Streamlit secrets.

OAuth app published "In production" - refresh tokens no longer expire weekly.

Folder: ARV Water system inven (id: 1lS3cITfDWRpto9wt4faxuYY9AH4Wqzan)

Upload filename: item_name_slug + timestamp + extension

---

## 8. Verification

- Manage Items screen loads with water-only list
- Adding an item with photo -> Drive upload works
- Pricing: 5087.17 cost -> 7630.76 with 50% markup
- Dropdowns populated from lookup_options (7 / 10 / 14)
- Single-domain water user sees only water domain
- Admin sees domain switcher + Pending Lookups badge

---
## 9. Roadmap

| Priority | Task | Status |
|---|---|---|
| 1 | Historical reporting stack | DONE |
| 2 | Multi-domain access foundation | DONE |
| 3 | User management + checkboxes | DONE |
| 4 | Water domain foundation | DONE |
| 5 | Water: Stock IN / Stock OUT screens | NEXT |
| 6 | Water: Dashboard, Reports | after 5 |
| 7 | Water: Low stock, physical inventory | after 5 |
| 8 | Domain-aware unified reporting | after 6 |
| 9 | Extract shared engine to core/ | after 8 |
| 10 | Admin approval workflow | unblocked |
| 11 | Edit-user access flags UI | deferred |

---
## 10. Design Decisions Made This Arc

Single warehouse column - not separate tables per domain. Isolation is a query filter.

Reuse master_items for water - not a separate water_items table. 8 new nullable columns.

Lookup options in DB - not hardcoded in config.py. Extendable via approval workflow.

Submit-then-approve for lookups, admin bypass. Users get pending; admins get approved immediately.

Drive OAuth with personal account - not service account. Files owned by user, folder-scoped.

role column left as write-through. Access decisions use the 3 flags.

Water module matches existing RPC conventions. Stock via record_stock_transaction and batch RPCs. Item CRUD direct insert like register_item.

---
## 11. Session Constraints (new this arc)

12. PowerShell ROOT anchoring - use absolute paths, never relative, when writing multiple files.

13. Streamlit secrets in bare python - st.secrets DOES load .streamlit/secrets.toml from cwd.

14. Placeholder values are dangerous - warn explicitly when writing setup examples.

15. PostgREST blocks arbitrary SQL - use Supabase SQL editor for DDL. Seeding via insert works.

16. Anchor-verify-then-replace patch scripts - always check anchor exists first.

17. Long here-string pastes can be killed by Ctrl+C - break into smaller pieces or use $lines += pattern.

---
## 12. Freeze Declaration

Snapshot v15.4 captures the state after the water system domain shipped with a working Manage Items screen, DB-backed lookup approval workflow, and Drive image upload.

The general warehouse path is byte-for-byte unchanged from v15.3. Water items live in the same master_items table, filtered by warehouse='watersystem'.

Frozen on: 2026-10-08
Next snapshot: v15.5
Next snapshot trigger: after Water domain Stock IN / Stock OUT screens ship.
