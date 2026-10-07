# SNAPSHOT_v15.md

> **ARV — Historical Reporting Stack Complete**
> Date: 2026-10-07
> Baseline: SNAPSHOT_v14.md
> Status: **FROZEN**

---

## 1. What Shipped Since v14

| Item | Status |
|---|---|
| Historical Transaction Date (Stock IN + Stock OUT) | OK |
| Sort by entry time (created_at DESC, timestamp DESC) | OK |
| Logged At column on all history/audit views | OK |
| Emoji encoding recovery (PS 5.1 damage reversed) | OK |
| Baseline seed rows for 41 items (Phase 1) | OK |
| Historical stock column in reports (Phase 2) | OK |
| Reports stay business-date-primary | OK |

---

## 2. Repo State

| Item | Value |
|---|---|
| HEAD commit | 271d5f8 |
| Branch | main (tracking origin/main) |
| Remote | https://github.com/m4rone2021/ARV.git |
| Live URL | https://arvinventory.streamlit.app |
| Supabase project | dirgeqpjpisfiawxihqw |

---

## 3. Ledger State (Supabase)

| Metric | Value |
|---|---|
| master_items rows | 41 |
| transactions rows | 252 (211 activity + 41 baseline seeds) |
| Ledger date range | 2026-09-15 to present |
| Baseline seed timestamp | 2026-09-15T00:00:00+00:00 |
| Baseline seed tag | handled_by = system-baseline, notes LIKE BASELINE SEED% |
| item_id backfill | 252/252 linked, 0 orphaned |
| Reconciliation | 0 variance across all 41 items |

### Ledger semantics
- IN -> adds to stock
- OUT -> subtracts from stock
- ADJUSTMENT -> sets absolute value (not delta)
- RECONCILIATION -> no-op
- Only edit_status = ACTIVE rows count

---

## 4. Feature — Historical Reporting

### Stock IN / Stock OUT
- User picks a Transaction Date (default: today)
- Stored as 23:59:59 UTC on that day
- Report-grade backdating enabled

### Reports
- Transaction reports show dynamic column Stock (as of YYYY-MM-DD) computed by forward-replaying the ledger up to the report end date
- Snapshot reports unchanged
- Screen preview, PDF, and Excel exports all include the new column

### Helper
views/reports.py: _stock_as_of(target_date) — forward-replays ACTIVE transactions up to end of the target date

### Verified
Movement Report for 2026-09-22 showed Diesel = 2823, matching the ledger running balance exactly.

---

## 5. Roadmap

| Priority | Task | Effort |
|---|---|---|
| 1 | Historical reporting stack | DONE |
| 2 | Admin approval workflow (edit/void/physical count) | ~4 hours |
| 3 | Route User Edit/Void through approval | ~1 hour |
| 4 | register_item() writes seed row on create | 15 min |
| 5 | Multi-warehouse support | ~1.5 days |

---

## 6. Freeze Declaration

Snapshot v15 captures the state after the full historical reporting stack shipped and was verified end-to-end.

**Frozen on:** 2026-10-07
**Next snapshot:** v16
**Next snapshot trigger:** after Admin Approval Workflow ships