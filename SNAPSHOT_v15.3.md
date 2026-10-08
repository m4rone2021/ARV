# SNAPSHOT_v15.3.md

> **ARV — User Management Complete, Access Model Fully Wired**
> Date: 2026-10-08
> Baseline: SNAPSHOT_v15.2.md (frozen 2026-10-08)
> Status: **FROZEN**

---

## 1. What Shipped Since v15.2

| Item | Status |
|---|---|
| `user_management.py` — three access checkboxes on create | OK |
| `user_management.py` — user table shows General/Water/Admin glyph columns | OK |
| `user_management.py` — `is_admin` auto-grants both domains on create | OK |
| `user_management.py` — reject create with zero flags | OK |
| `user_management.py` — password-confirmed delete (admin's own password) | OK |
| `user_management.py` — delete last-admin guard reads `is_admin` flag | OK |
| `role` column write-through preserved (`'Admin'` / `'User'`) for legacy reads | OK |

---

## 2. Repo State

| Item | Value |
|---|---|
| HEAD commit | (to be filled after push) |
| Branch | main (tracking origin/main) |
| Remote | https://github.com/m4rone2021/ARV.git |
| Live URL | https://arvinventory.streamlit.app |
| Supabase project | dirgeqpjpisfiawxihqw |

### Commit timeline (this arc)
- d794572 feat: login_user returns access flags (general/water/admin)
- c34132c feat: app.py domain switcher + access-flag routing
- d204daa docs: SNAPSHOT_v15.2 — multi-domain access foundation
- (HEAD)   feat(user_mgmt): three access checkboxes + password-confirmed delete

---

## 3. Access Model — Fully Live

### Two independent axes

| Axis | Column | Purpose |
|---|---|---|
| Domain | `access_general` | Construction warehouse |
| Domain | `access_watersystem` | Water system inventory |
| Overlay | `is_admin` | Both domains + user management |

### Behavior matrix

| User type | Domain switcher | Domain access | Admin tools | User mgmt |
|---|---|---|---|---|
| Single-domain | hidden | 1 domain | no | no |
| Dual-domain | shown (radio) | both | no | no |
| Admin | shown (radio) | both | yes | yes |
| No flags | n/a | rejected | n/a | n/a |

### Session state keys

| Key | Source | Cleared on logout |
|---|---|---|
| `user_access_general` | `user_data.access_general` | yes |
| `user_access_watersystem` | `user_data.access_watersystem` | yes |
| `user_is_admin` | `user_data.is_admin` | yes |
| `active_domain` | derived at login | yes |

---

## 4. User Management — Safety Behavior

### Create user

- Three checkboxes: **General Warehouse** / **Water System** / **Administrator**
- Admin checked → both domains auto-granted
- Zero flags → rejected with clear error
- `role` column written as `'Admin'` if `is_admin` else `'User'` (backwards compat)

### Delete user

- Two-step: **Request Delete** → **Confirm Delete** with password prompt
- Password verified against the **logged-in admin's own** account (sudo pattern)
- Wrong password → no delete, red error
- Empty password → no delete
- Cancel → prompt dismissed, no delete
- Last-admin guard: cannot delete the last remaining `is_admin = true` row
- Cannot delete own account (self not in deletable list)

### Still missing (future work)

- Edit existing user's access flags (no UI yet, only SQL)
- Activate / deactivate toggle
- Force password reset button in UI
- User list filter by domain

---

## 5. Ledger State (Supabase)

Unchanged from v15.2:

| Metric | Value |
|---|---|
| `master_items` | 41 (all `construction`) |
| `transactions` | 324 (all `construction`) |
| `deliveries` | 0 (empty) |
| `reminders` | 0 (empty) |
| `users` | 2 (admin, ross) + test users created during verification |

---

## 6. Roadmap

| Priority | Task | Status |
|---|---|---|
| 1 | Historical reporting stack | DONE (v15.1) |
| 2 | Multi-domain access foundation | DONE (v15.2) |
| 3 | User management + access checkboxes | DONE (v15.3) |
| 4 | Build `watersystem/` module | NEXT |
| 5 | Domain-aware reports | after 4 |
| 6 | Extract shared ledger engine to `core/` | after 4-5 |
| 7 | Admin approval workflow | unblocked |
| 8 | Edit-user access flags UI | deferred |
| 9 | Multi-warehouse beyond water | future |

---

## 7. Design Decisions Made This Arc

### Domains live in a single table, tagged by column

Not separate tables per domain. `master_items`, `transactions`, `deliveries` all carry `warehouse TEXT NOT NULL DEFAULT 'construction'`. Domain isolation is a query filter, not a table split. Reasoning: shared ledger engine, single migration path, trivially extensible to a third domain later.

### User access is two booleans + admin flag

Not an enum, not a role table. `access_general`, `access_watersystem`, `is_admin`. All three can be checked independently. Admin auto-grants domains on create. Special-cased users can have both domain flags.

### Admin is an overlay, not a domain

Admin users see the same domain switcher as dual-domain users. The admin capability adds a User Management menu item, not a third domain.

### `role` column left as write-through

Legacy reads in `app.py` (`st.session_state.user_role`) and display strings still use `role`. We write it consistently on user creation but no longer read it for access decisions. Eventual cleanup is a future task.

### Destructive actions require password re-verification

Delete user is now the first such action. The pattern (session flag → password prompt → verify against logged-in user → execute) should be reused for future destructive operations: void transaction, bulk delete, physical inventory commit, etc.

---

## 8. Session Constraints (unchanged from v15.2 §7)

All ten constraints still apply. The most relevant this arc:

- **Rule 4:** always `ast.parse` after patching — caught nothing but reassuring
- **Rule 9:** anchored patches fail loud if anchor missing — used 3 times cleanly
- **Rule 10:** print patched region for visual confirmation — followed

### New constraint (learned this arc)

11. When patching a Streamlit form for a two-step flow (click → confirm),
    convert the outer form to plain widgets (`st.selectbox` + `st.button`) so
    the intermediate state can live in `st.session_state` across reruns.
    Forms clear on submit and swallow intermediate state.

---

## 9. Freeze Declaration

Snapshot v15.3 captures the state after user management was brought into the
new access model. All access decisions now flow through `access_general`,
`access_watersystem`, and `is_admin`. The `role` column is vestigial. Destructive
actions have password confirmation. The general warehouse path is byte-for-byte
unchanged from v15.2 apart from the improvements to user management itself.

**Frozen on:** 2026-10-08
**Next snapshot:** v15.4
**Next snapshot trigger:** after the first `watersystem/` screen ships.