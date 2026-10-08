# SNAPSHOT_v15.5.md

> **ARV - Water Stock Movement Complete**
> Date: 2026-10-08
> Baseline: SNAPSHOT_v15.4.md (frozen 2026-10-08)
> Status: **FROZEN**

---

## 1. What Shipped Since v15.4

| Item | Status |
|---|---|
| Water Stock IN screen | OK |
| Water Stock OUT screen | OK |
| `warehouse` param on both batch RPCs | OK |
| Old 6-arg RPC signatures dropped | OK |
| Construction history filtered to construction | OK |
| Water history filtered to watersystem | OK |
| Cross-domain leakage prevented | OK |

---
## 2. Repo State

| Item | Value |
|---|---|
| HEAD commit | 2a031ec |
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
- 43805b4 docs: SNAPSHOT_v15.4 - water system domain shipped
- 2a031ec feat(watersystem): Stock IN / Stock OUT + warehouse-scoped batch RPCs

---
## 3. RPC Changes

Both batch RPCs gained a new parameter:

```
p_warehouse text DEFAULT 'construction'
```

### receive_stock_batch_atomic

- New signature: (p_supplier, p_dr_number, p_handled_by, p_general_notes, p_items, p_transaction_date, p_warehouse)
- Item validation: WHERE item_name = v_item_name AND warehouse = p_warehouse
- Stock update: WHERE item_name = v_item_name AND warehouse = p_warehouse
- transactions insert now writes warehouse = p_warehouse

### issue_stock_batch_atomic

- New signature: (p_requested_by, p_destination, p_project, p_handled_by, p_items, p_transaction_date, p_warehouse)
- Stock validation with FOR UPDATE: WHERE item_name = v_item_name AND warehouse = p_warehouse
- Stock deduction: WHERE item_name = v_item_name AND warehouse = p_warehouse
- transactions insert now writes warehouse = p_warehouse

### Old signatures dropped

```sql
DROP FUNCTION IF EXISTS public.receive_stock_batch_atomic(text, text, text, text, jsonb, timestamptz);
DROP FUNCTION IF EXISTS public.issue_stock_batch_atomic(text, text, text, text, jsonb, timestamptz);
```

Only the 7-arg versions remain callable.

---
## 4. database.py Patch

Both batch functions gained an optional parameter:

```python
def receive_stock_batch(..., transaction_date=None, warehouse='construction'):
def issue_stock_batch(..., transaction_date=None, warehouse='construction'):
```

The warehouse value is passed into the RPC as `p_warehouse`.

Existing construction callers do not pass it and get the default. Zero behavior change.

---
## 5. Water Stock Screens

### watersystem/screens/stock_in.py

- Batch receive form for water items
- Item picker filters `warehouse='watersystem'`
- History tab filters `warehouse='watersystem'`
- Calls receive_stock_batch(..., warehouse='watersystem')

### watersystem/screens/stock_out.py

- Batch issue form for water items
- Item picker filters `warehouse='watersystem'`
- History tab filters `warehouse='watersystem'`
- Calls issue_stock_batch(..., warehouse='watersystem')

### Sidebar menu

Water domain now shows:

```
Water System
  Manage Items
  Stock IN
  Stock OUT
  Pending Lookups (N)  [admin only]
```

---
## 6. Construction History Fix

Added `.eq('warehouse', 'construction')` to both history queries in views/stock_in.py and views/stock_out.py.

Without this, once water items existed, they would appear in the construction history tables. The filter isolates them.

---
## 7. Verification

Ran a real water Stock IN and Stock OUT after the change:

```
type,item_name,warehouse,created_at
OUT,SLEEVE TYPE COUPLING,watersystem,2026-10-08 06:42:04
IN,SLEEVE TYPE COUPLING,watersystem,2026-10-08 06:41:20
IN,Grinding Stone,construction,2026-10-08 02:08:01
```

Water transactions tagged with `warehouse='watersystem'`. Construction unaffected. No cross-contamination.

Construction Stock IN history continues to show only construction items.

---
## 8. Roadmap

| Priority | Task | Status |
|---|---|---|
| 1 | Historical reporting stack | DONE |
| 2 | Multi-domain access foundation | DONE |
| 3 | User management + checkboxes | DONE |
| 4 | Water domain foundation | DONE |
| 5 | Water Stock IN / Stock OUT | DONE |
| 6 | Water: Dashboard, Reports | NEXT |
| 7 | Water: Low stock alerts, physical inventory | after 6 |
| 8 | Domain-aware unified reporting | after 6 |
| 9 | Extract shared engine to core/ | after 8 |
| 10 | Admin approval workflow | unblocked |
| 11 | Edit-user access flags UI | deferred |

---
## 9. Design Decisions Made This Arc

**RPCs parameterized, not duplicated.** Two batch RPCs gained `p_warehouse` with a default of `'construction'`. Backwards-compatible for existing callers. No water-specific RPC copies to maintain.

**Old signatures dropped.** Adding a parameter changed the PostgreSQL function signature, so CREATE OR REPLACE created a second overload. Both old and new existed briefly. Old ones dropped to prevent accidental use with default warehouse.

**Python side matches RPC default.** `database.py` wrappers default `warehouse='construction'`, mirroring the SQL default. Construction views call unchanged. Water views pass `warehouse='watersystem'` explicitly.

**History queries are domain-filtered at the source.** Both construction and water history tabs use `.eq('warehouse', ...)`. No post-filtering, no cross-domain leakage. Every query that reads transactions now says which domain it wants.

**Water screens are structurally identical to construction.** Same UX, same session-state cart pattern, same submit flow. Just warehouse-scoped. Users who know the construction screens know the water ones.

---
## 10. Session Constraints (new this arc)

18. **PostgreSQL CREATE OR REPLACE does not replace functions with different argument lists.** Adding a parameter, even with a default, creates a new overload. Old version must be explicitly dropped with DROP FUNCTION IF EXISTS matching the old signature.

19. **Verify function signatures after DDL with pg_proc.** Query proname + pg_get_function_arguments to confirm exactly one version of each function exists. Duplicate overloads are silent bugs.

20. **Parameterize before duplicating.** When two domains need near-identical database logic, adding a parameter with a domain default is cleaner than copying the function. The water/construction split for batch RPCs is the template.

---

## 11. Freeze Declaration

Snapshot v15.5 captures the state after water system Stock IN and Stock OUT shipped, with warehouse-scoped batch RPCs on both domains and history queries filtered at the source.

Water items can now be received into and issued from the water system warehouse. Transactions are tagged correctly. Construction is unaffected.

Frozen on: 2026-10-08
Next snapshot: v15.6
Next snapshot trigger: after Water domain Dashboard or Reports ship.
