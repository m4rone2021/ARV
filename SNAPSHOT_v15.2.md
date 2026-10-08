# SNAPSHOT_v15.2.md

> **ARV — Multi-Domain Access Foundation Complete**
> Date: 2026-10-08
> Baseline: SNAPSHOT_v15.md (v15.1, frozen 2026-10-08)
> Status: **FROZEN**

---

## 1. What Shipped Since v15.1

| Item | Status |
|---|---|
| `warehouse` column on `master_items` (41 rows, all `construction`) | OK |
| `warehouse` column on `transactions` (324 rows, all `construction`) | OK |
| `warehouse` column on `deliveries` (empty table, ready) | OK |
| `users.access_general` boolean flag | OK |
| `users.access_watersystem` boolean flag | OK |
| `users.is_admin` boolean flag | OK |
| Backfill: existing users -> `access_general = true` | OK |
| Promote `admin` account -> `is_admin = true` | OK |
| `login_user` returns three access flags | OK |
| `app.py` domain switcher (admin + dual-access users) | OK |
| `app.py` routing by `active_domain` | OK |
| Water domain placeholder ("under construction") | OK |
| No-access guard page for users with zero flags | OK |
| Water-domain sidebar hides general menu | OK |

---

## 2. Repo State

| Item | Value |
|---|---|
| HEAD commit | c34132c |
| Branch | main (tracking origin/main) |
| Remote | https://github.com/m4rone2021/ARV.git |
| Live URL | https://arvinventory.streamlit.app |
| Supabase project | dirgeqpjpisfiawxihqw |

### Commit timeline (this arc)
- d794572 feat: login_user returns access flags (general/water/admin)
- c34132c feat: app.py domain switcher + access-flag routing

---

## 3. Ledger State (Supabase)

| Metric | Value |
|---|---|
| `master_items` rows | 41 (all `warehouse='construction'`) |
| `transactions` rows | 324 (all `warehouse='construction'`) |
| `deliveries` rows | 0 (empty, `warehouse` column added) |
| `reminders` rows | 0 (empty) |
| `discrepancies` rows | (unchanged) |
| `physical_inventory_logs` rows | (unchanged) |
| Ledger date range | 2026-09-15 to present |

### Users

| username | access_general | access_watersystem | is_admin | is_active |
|---|---|---|---|---|
| admin | true | true | true | true |
| ross  | true | false | false | true |

(Note: `liway` no longer present — deleted or renamed between v15.1 and v15.2.)

---

## 4. Access Model

### Two independent axes

**Domain access** (booleans on `users`):
- `access_general` — construction warehouse
- `access_watersystem` — water system inventory

**Admin overlay** (boolean on `users`):
- `is_admin` — full access to both domains + user management

### Behavior

- Single-domain user (e.g. `ross`) — no switcher, dropped straight into their domain
- Dual-domain user — sidebar domain switcher (radio), one active at a time
- Admin — same switcher + Admin Tools / User Management overlay
- Zero flags — "No inventory access assigned" page with logout

### Routing

`app.py:render_app()` reads `st.session_state.user_access_general`, `user_access_watersystem`, `user_is_admin`. Builds `_domains` list. If len > 1, renders sidebar radio switcher. `active_domain` determines which branch renders.

General branch: existing behavior, unchanged.

Water branch: placeholder page + logout button only.

---

## 5. session_state Keys (new)

| Key | Type | Purpose |
|---|---|---|
| `user_access_general` | bool | mirrors `users.access_general` |
| `user_access_watersystem` | bool | mirrors `users.access_watersystem` |
| `user_is_admin` | bool | mirrors `users.is_admin` |
| `active_domain` | str or None | `'general'` or `'watersystem'` |

All four cleared on logout (both logout paths).

---

## 6. Roadmap

| Priority | Task | Status |
|---|---|---|
| 1 | Historical reporting stack | DONE (v15.1) |
| 2 | Multi-domain access foundation | DONE (v15.2) |
| 3 | `user_management.py` — three access checkboxes | NEXT |
| 4 | Water-only test user + end-to-end routing verification | NEXT |
| 5 | Build `watersystem/` module (items, transactions, views) | after 3-4 |
| 6 | Domain-aware reports (general / water scoping) | after 5 |
| 7 | Extract shared ledger engine to `core/` | after 5-6 |
| 8 | Admin approval workflow (edit/void/physical count) | unblocked |
| 9 | Multi-warehouse beyond water (electrical, tools) | future |

---

## 7. Session Constraints (inherited from v15.1 §6)

**Read before patching any file:**

1. NEVER use PowerShell `Set-Content -Encoding utf8` on .py files.
   PS 5.1 writes UTF-8 with BOM and mis-decodes non-ASCII, causing emoji mojibake.

2. ALWAYS use Python for reading/writing:
   - Read: `path.read_text(encoding="utf-8")`
   - Write: `path.write_bytes(text.encode("utf-8"))`
   - Or from PowerShell: `[System.IO.File]::WriteAllText($path, $content, (New-Object System.Text.UTF8Encoding $false))`

3. Write Python patch scripts via here-string + `[IO.File]::WriteAllText` with `$false` BOM flag.
   Never use `Set-Content`.

4. After every patch: run `python -c "import ast; ast.parse(open(...).read())"` to verify syntax.

5. Backup before each patch (`path.bak_<timestamp>`) but exclude backups from git.

6. One file at a time. Verify after each. Do not batch.

7. Bash `Get-Content` and PowerShell `Select-String` mis-render UTF-8 to the console.
   Trust the file bytes, not the console output.

8. `-Include '_*.py'` on `Get-ChildItem -Recurse` matches `__init__.py` — use explicit
   `Where-Object { $_.Name -like '_*.py' -and $_.Name -notlike '__init__.py' }` instead.

### New constraint (learned this arc)

9. Anchored replacement patches MUST verify the anchor exists before replacing, and exit
   non-zero if not found. PowerShell wrapper restores the timestamped backup automatically
   on non-zero exit. This pattern has shipped cleanly twice this session (`database.py`,
   `app.py`).

10. After patch, print the patched region for visual confirmation. Do not silently commit.

---

## 8. Freeze Declaration

Snapshot v15.2 captures the state after the multi-domain access foundation shipped.
`app.py` routes by user flags, water domain exists as a placeholder, and the general
warehouse path is byte-for-byte unchanged from v15.1.

**Frozen on:** 2026-10-08
**Next snapshot:** v15.3
**Next snapshot trigger:** after `user_management.py` checkboxes ship and water-only
test user is verified end-to-end.