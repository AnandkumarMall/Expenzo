# Spec: Delete Expense

## Overview
Let a logged-in user delete one of their own existing expenses via a confirmation page at `/expenses/<id>/delete`. The page shows what is about to be deleted (date, category, amount, description), lets the user confirm with a single `Delete expense` button, and on confirmation permanently removes the row from `expenses` before redirecting to `/profile` so the change is immediately visible in the recent-transactions table. A `Cancel` link returns the user to `/profile` without deleting. This step replaces the existing Step 9 stub (`return "Delete expense — coming in Step 9"`) and completes the per-row CRUD story: the user can now `POST /expenses/add` (Step 7), `GET/POST /expenses/<id>/edit` (Step 8), and `GET/POST /expenses/<id>/delete` (this step). The entry point is a `Delete` link in the recent-transactions table on `/profile`, sitting next to the `Edit` link that Step 8 already wired up.

## Depends on
- 01-database-setup — `expenses` table must exist with `(id, user_id, amount, category, date, description, created_at)`
- 02-registration — accounts must be creatable
- 03-login-and-logout — `session['user_id']` must be set when reaching `/expenses/<id>/delete`
- 04-profile-page-design — the recent-transactions table is where the Delete link is rendered
- 05-backend-route-for-profile-page — `/profile` must read real rows so the delete link has a target
- 06-date-filter-for-profile-page — optional but helpful: the deleted row's `date` is no longer in the recent-transactions table
- 07-add-expense — the row-lookup pattern in `add_expense_to_db` and the row-insertion style
- 08-edit-expense — the row-fetch + ownership-check pattern in `get_expense_by_id` is the template for this step; the delete route reuses the same helper

## Routes
- `GET /expenses/<int:id>/delete` — fetch the row (404 if missing or owned by another user), render the confirmation page with the row's fields displayed for review — logged-in only (redirect to `/login` if not authenticated)
- `POST /expenses/<int:id>/delete` — fetch the row (404 if missing or owned by another user), delete the row, redirect to `/profile` on success — logged-in only

No new routes. The URL is the same shape as the existing Step 9 stub (`/expenses/<int:id>/delete`); only the implementation changes.

## Database changes
No database changes. The `expenses` table from Step 1 already supports `DELETE`. The DB-layer change in this step is a single new helper, `delete_expense(user_id, expense_id)`, that runs one parameterised `DELETE` guarded by `user_id` so a user can never delete another user's row even if they guess the id.

## Templates
- **Create:** `templates/delete_expense.html` — extends `base.html`, displays the row's date, category, amount, and description in a read-only summary, with a single `Delete expense` submit button and a `Cancel` link back to `url_for('profile')`. No form fields — the route is a one-way destructive action that needs a confirmation step.
- **Modify:** `templates/profile.html` — add a `Delete` link in the recent-transactions table's `Actions` cell, next to the `Edit` link Step 8 already wired up. The Delete link targets `url_for('delete_expense', id=tx.id)`. No layout changes; the cell already exists.

## Confirmation page (UI)
The confirmation page is intentionally minimal. It does not look like the add/edit form — it looks like a destructive confirmation, with the about-to-be-deleted row clearly displayed so the user can confirm they have the right one.

- A single centered card (same `.auth-section` / `.auth-container` / `.auth-card` styling as add/edit).
- A small header line that reads `Delete expense` with a subtitle `This action cannot be undone.`
- A read-only summary of the row: `Date`, `Category`, `Amount` (formatted as `₹<amount>` via `format_inr`), `Description` (or `—` when `NULL`).
- A `<form method="POST" action="{{ url_for('delete_expense', id=expense.id) }}">` containing only the submit button.
- A single primary destructive button labelled `Delete expense` (red/danger styling).
- A `Cancel` link back to `url_for('profile')` that does not submit the form.

There are no input fields on this page — there is nothing for the user to type. The only "input" is the button click.

## Validation rules
There are no form fields to validate. The route does no client-side or server-side input checking beyond the auth gate and the row-ownership check. The only "rule" is that the row must exist and belong to the logged-in user, which is enforced the same way Step 8 does it: `abort(404)` otherwise.

## Ownership and 404 handling
The route must not leak the existence of another user's row. Two cases, both `abort(404)`:

- The id does not exist in `expenses` at all → 404
- The id exists but its `user_id` does not match `session['user_id']` → 404 (not 403, to avoid confirming the row's existence)

This check happens on both `GET` and `POST`, before any form read or write, so a logged-in user can never reach the confirmation page or successfully POST a delete for a row they do not own. This reuses the existing `get_expense_by_id(user_id, expense_id)` helper from Step 8.

## Redirect / success
On a successful delete, redirect (HTTP 302) to `url_for('profile')`. The change will be visible in the recent-transactions table because the row is gone. No flash message is required at this step — the redirect is the feedback.

## CSRF and idempotency
- The route is auth-gated: a GET or POST without `session['user_id']` redirects to `/login` and does not delete.
- The route is NOT idempotent in the strict sense — a second POST after a successful delete will 404 (the row is gone). This is the desired behaviour: the user can never accidentally re-delete the same row by double-clicking the button on a slow connection because the first click returns a 302 and the browser navigates away.
- The route accepts only `GET` (confirmation) and `POST` (commit). Other methods (e.g. `PUT`, `DELETE`) are not bound; Flask returns 405 for them.

## Files to change
- `app.py` — replace the `delete_expense` stub with a real `GET` + `POST` handler. The `GET` branch fetches the row (404 if missing/foreign) and renders the confirmation template. The `POST` branch fetches the row (404 if missing/foreign), calls `delete_expense(user_id, id)`, and redirects to `/profile`.
- `database/db.py` — add `delete_expense(user_id, expense_id)` — a single parameterised `DELETE FROM expenses WHERE id = ? AND user_id = ?`, committing and returning the rowcount so the route can confirm the row was actually deleted (a missing/foreign row will return 0 and the route can 404 if it ever does, but the pre-flight `get_expense_by_id` makes that path unreachable in practice).
- `templates/profile.html` — add a `Delete` link to each row in the recent-transactions table's `Actions` cell, next to the `Edit` link. The link is a small text link in a danger colour (via a CSS variable), not a primary button, to keep the table visually quiet.

## Files to create
- `templates/delete_expense.html` — the confirmation page (read-only summary + submit + cancel).
- `static/css/delete-expense.css` — page-specific styles. Most styles are already on `.auth-section` / `.auth-card` / `.expense-form-actions`; the new file is small and only adds delete-specific tweaks (e.g. the `.delete-summary` row layout, the `.btn-danger` destructive button). Follows the same CSS-variable convention. No hex values.

## New dependencies
No new dependencies. No new pip packages, no new JS packages, no CDN scripts. The page is pure server-rendered HTML and CSS.

## New helper in `database/db.py`
- `delete_expense(user_id, expense_id)` — run `DELETE FROM expenses WHERE id = ? AND user_id = ?`, commit, and return the number of affected rows. All values are passed as parameters — no f-strings in SQL. The `user_id` guard ensures a user can never delete another user's row. The pre-flight `get_expense_by_id` call in the route makes a 0-rowcount result unreachable in practice, but the helper still returns it so a future caller (e.g. a bulk-delete admin tool) can detect a no-op.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()` only
- Parameterised queries only — `?` placeholders for every value, including the `user_id` guard on the `DELETE`
- Passwords are not touched at this step; auth state is read from `session` only
- Use CSS variables — never hardcode hex values (the new `delete-expense.css` must follow the same `--var-name` pattern already in `style.css`, `add-expense.css`, and `edit-expense.css`)
- All templates extend `base.html` — no exceptions
- DB logic must reside in `database/db.py` — `app.py` only reads the form, calls helpers, renders
- Route functions have one responsibility only — fetch row, call helper, redirect or re-render
- Use `abort(404)` for missing rows and rows the user does not own — do not return a plain string, do not redirect, do not leak the row's existence with a 403
- Reuse the existing `get_expense_by_id(user_id, expense_id)` helper from Step 8 for the ownership check — do not write a new "exists for this user" query
- Use `url_for('delete_expense', id=expense.id)` for the form action and `url_for('profile')` for the cancel link — never hardcode paths
- The route must remain auth-gated: redirect to `/login` if `session.get("user_id")` is missing on both `GET` and `POST`
- `user_id` for the `DELETE` guard must come from `session['user_id']` — never from the form
- The route accepts only `GET` and `POST`; no other HTTP methods
- The confirmation page must clearly display the row's date, category, amount, and description so the user can confirm they are deleting the right row
- The destructive button uses a `btn-danger` class (CSS-variable colour, not a hardcoded hex) so it is visually distinct from the primary submit on the add/edit forms
- The page is intentionally server-rendered — no client-side JS beyond what `base.html` already loads
- The Cancel link must be a plain `<a href="...">` (not a `<button type="button">`) so it works without JavaScript
- The `Edit` link in `templates/profile.html` already targets `url_for('edit_expense', id=tx.id)` from Step 8; this step only adds the `Delete` link next to it. The cell's layout (right-aligned, with both links in a row) is unchanged
- The destructive action is irreversible at this step — there is no "undo" affordance and no soft-delete column. A later step could add a trash/recycle feature; this step does not

## Definition of done
- [ ] `GET /expenses/<id>/delete` (logged in, owns the row) renders the confirmation page with the row's date, category, amount, and description
- [ ] `GET /expenses/<id>/delete` (logged in, row belongs to another user) returns 404
- [ ] `GET /expenses/<id>/delete` (logged in, id does not exist) returns 404
- [ ] `GET /expenses/<id>/delete` (not logged in) redirects to `/login`
- [ ] `POST /expenses/<id>/delete` with a valid id (logged in, owns the row) deletes the row, commits, and redirects to `/profile`
- [ ] After a successful delete, the row no longer appears in the recent-transactions table on `/profile` without a manual refresh
- [ ] After a successful delete, the user's total spent, transaction count, top category, and category breakdown on `/profile` are all updated to reflect the deletion
- [ ] The `DELETE` statement's `WHERE` clause includes `user_id = ?` — a user can never delete another user's row even if they POST to the right id
- [ ] `POST /expenses/<id>/delete` (not logged in) redirects to `/login` and does not delete
- [ ] `POST /expenses/<id>/delete` (logged in, row belongs to another user) returns 404 and does not delete
- [ ] `POST /expenses/<id>/delete` (logged in, id does not exist) returns 404 and does not delete
- [ ] The confirmation page shows the row's `date` exactly as stored (e.g. `2026-05-29`)
- [ ] The confirmation page shows the row's `amount` formatted via `format_inr` (e.g. `₹45`)
- [ ] The confirmation page shows the row's `description` as the stored value, or `—` when `NULL`
- [ ] The confirmation page has a single `Delete expense` submit button and a single `Cancel` link
- [ ] The `Cancel` link returns to `/profile` without deleting
- [ ] The destructive button uses a `btn-danger` class (CSS-variable colour, not a hardcoded hex)
- [ ] No SQL in `app.py` — all deletes go through `database/db.py`
- [ ] All SQL uses `?` placeholders (no f-strings, no string concatenation)
- [ ] The new `delete_expense` helper is added to `database/db.py`
- [ ] The new template extends `base.html`
- [ ] The new CSS file is page-specific (`static/css/delete-expense.css`) and uses only CSS variables from `style.css`
- [ ] Each row in the recent-transactions table on `/profile` has a working `Delete` link to `url_for('delete_expense', id=tx.id)` (no `href="#"`, no hardcoded path), sitting next to the existing `Edit` link
- [ ] `pytest` still passes (no regressions in the existing test suite, including Step 7's add-expense tests and Step 8's edit-expense tests)
