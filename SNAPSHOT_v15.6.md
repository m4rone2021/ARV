# SNAPSHOT_v15.6.md

> **ARV - Water System Operational**
> Date: 2026-10-08
> Baseline: SNAPSHOT_v15.5.md (frozen 2026-10-08)
> Status: **FROZEN**

---

## 1. What Shipped Since v15.5

| Item | Status |
|---|---|
| `warehouse` on `physical_inventory_logs` | OK |
| `warehouse` on `discrepancies` | OK |
| Water Low Stock Alerts screen | OK |
| Water Physical Inventory screen | OK |
| Warehouse-aware discrepancy submit | OK |
| Warehouse-aware discrepancy approve/reject | OK |
| Warehouse-aware RECONCILIATION transactions | OK |
| Construction low_stock / physical_inventory scoped | OK |

---
## 2. Repo State

| Item | Value |
|---|---|
| HEAD commit | 67e410a |
| Branch | main (tracking origin/main) |
| Remote | https://github.com/m4rone2021/ARV.git |
| Live URL | https://arvinventory.streamlit.app |
| Supabase project | dirgeqpjpisfiawxihqw |

### Commit timeline (this arc)
- 2a031ec feat(watersystem): Stock IN / Stock OUT + warehouse-scoped batch RPCs
- cd1ceaa docs: SNAPSHOT_v15.5 - water stock movement complete
- 67e410a feat(watersystem): Low Stock Alerts + Physical Inventory, warehouse-aware discrepancy flow

---
## 3. SQL Changes

```sql
ALTER TABLE physical_inventory_logs ADD COLUMN IF NOT EXISTS warehouse TEXT NOT NULL DEFAULT 'construction';
ALTER TABLE discrepancies ADD COLUMN IF NOT EXISTS warehouse TEXT NOT NULL DEFAULT 'construction';
CREATE INDEX IF NOT EXISTS idx_pil_warehouse ON physical_inventory_logs(warehouse);
CREATE INDEX IF NOT EXISTS idx_disc_warehouse ON discrepancies(warehouse);
```

Existing rows (16 in each table) backfilled to `construction`.

---
## 4. Water Screens Added

### watersystem/screens/low_stock.py

- Reads `master_items` filtered to `warehouse='watersystem'`
- Computes `effective_stock = current_stock - reserved_stock`
- Flags items where `effective_stock <= min_threshold`
- Cards view and table view
- (Restock scheduling omitted for now; construction has it, water does not yet)

### watersystem/screens/physical_inventory.py

- Item picker filters `warehouse='watersystem'`
- Submits counts to `physical_inventory_logs` with `warehouse='watersystem'`
- Non-zero variance submits to `discrepancies` with `warehouse='watersystem'`
- Admin sees pending water discrepancies only
- Approve: updates `master_items` (warehouse-filtered), inserts RECONCILIATION transaction (warehouse-tagged)
- Reject: preserves system stock, marks discrepancy as REJECTED
- History tab scoped to water discrepancies only

---
## 5. Construction Views Patched

### views/low_stock.py

- Item query now filters `warehouse='construction'`
- Delivery schedule insert writes `warehouse='construction'`

### views/physical_inventory.py (6 edits)

- Item picker query: `warehouse='construction'`
- `physical_inventory_logs` insert: `warehouse='construction'`
- `discrepancies` insert: `warehouse='construction'`
- Pending discrepancies query: `warehouse='construction'`
- Approve flow master_items update: `.eq('warehouse', 'construction')`
- Approve flow RECONCILIATION insert: `warehouse='construction'`
- History query: `warehouse='construction'`

---
## 6. Verification

Real RECONCILIATION transactions after the change:

```
type,item_name,warehouse,notes
RECONCILIATION,FLANGE RING,watersystem,Discrepancy Approved. Diff: -10.00 pcs. Reason: confirmed damage
RECONCILIATION,Fujiweld,construction,Discrepancy Approved. Diff: -3.00 pcs. Reason: Reviewed and investigated
RECONCILIATION,Coolant,construction,Discrepancy Approved. Diff: +1.00 pcs. Reason: Reviewed the records
```

Water and construction reconciliations are cleanly separated by warehouse.

Master stock confirmation: FLANGE RING updated from 20 to 10 after approving a -10 deficit discrepancy.

---
## 7. Roadmap

| Priority | Task | Status |
|---|---|---|
| 1 | Historical reporting stack | DONE |
| 2 | Multi-domain access foundation | DONE |
| 3 | User management + checkboxes | DONE |
| 4 | Water domain foundation | DONE |
| 5 | Water Stock IN / Stock OUT | DONE |
| 6 | Water Low Stock Alerts + Physical Inventory | DONE (v15.6) |
| 7 | Water Dashboard | NEXT |
| 8 | Water Reports | NEXT |
| 9 | Domain-aware unified reporting | after 8 |
| 10 | Extract shared engine to core/ | after 9 |
| 11 | Admin approval workflow (edit/void) | unblocked |
| 12 | Edit-user access flags UI | deferred |
| 13 | Water restock scheduling (low_stock form) | deferred |

---
## 8. Design Decisions Made This Arc

**Warehouse column on every table that touches stock.** physical_inventory_logs, discrepancies, transactions, master_items, deliveries - all have a warehouse column with default 'construction'. Every read and write specifies the domain.

**Every reconciliation goes through a discrepancy.** Physical counts do not directly update master_items. They create a discrepancy row. Admin approves and only then does master_items change. This is the check-and-balance pattern.

**Reject preserves system stock.** If the admin rejects a discrepancy, nothing changes. The system keeps its balance. This supports the workflow where damage is contested, someone has to pay, or investigation is inconclusive.

**Water screens mirror construction shape.** Same UX, same cart pattern, same tabs. Users move between domains without relearning.

**restock scheduling deferred for water.** Construction low_stock has a delivery-scheduling form. Water does not yet. Add when the workflow is needed.

---

## 9. Session Constraints (new this arc)

21. **UTF-8 BOM in legacy files causes ast.parse to fail.** Some legacy .py files (views/low_stock.py) start with a UTF-8 BOM. Read with `encoding='utf-8-sig'` when parsing, or strip the BOM at read time. Python itself tolerates the BOM at import.

22. **Admin approval as a pattern.** The lookup_options approval workflow and the discrepancies approval workflow share the shape: user submits pending, admin approves or rejects with reason, action applies only on approve. This is the reusable pattern for future admin-gated operations (edit/void, bulk delete, etc.).

---

## 10. Freeze Declaration

Snapshot v15.6 captures the state after water system Low Stock Alerts and Physical Inventory shipped, with warehouse-aware discrepancy submission, approval, and reconciliation.

Every stock-modifying workflow now respects the warehouse boundary. Water and construction operations are fully isolated. The admin approval pattern is established in two places (lookups, discrepancies) and is ready to be reused for future admin-gated operations.

Frozen on: 2026-10-08
Next snapshot: v15.7
Next snapshot trigger: after Water domain Dashboard or Reports ship.
