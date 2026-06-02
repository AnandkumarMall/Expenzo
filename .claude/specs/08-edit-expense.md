# Spec: Edit Expense

## Overview
Let a logged-in user edit one of their own existing expenses from a dedicated `/expenses/<id>/edit` page. The page pre-fills the form with the row's current values, validates input with the same rules as Step 7 (add), persists the update to the existing `expenses` row, and redirects to `/profile` so the change is immediately reflected. This step turns the existing Step 8 stub into a working edit flow and is the prerequisite for Step 9 (delete), since both routes share the same row-lookup + ownership-check pattern. Edit is intentionally an authenticated, per-row operation — there is no "edit list" page; the entry point lives on the recent-transactions table that Step 5 already renders.

## Depends on
- 01-database-setup — `expenses` table must exist with `(id, user_id, amount, category, date, description, created_at)`
- 02-registration — accounts must be creatable
- 03-login-and-logout — `session['user_id']` must be set when reaching `/expenses/<id>/edit`
- 04-profile-page-design — the recent-transactions table is where the Edit link is rendered
- 05-backend-route-for-profile-page — `/profile` must read real rows so the edit link has a target
- 06-date-filter-for-profile-page — optional but helpful: the edited row's `date` is rendered correctly by the date-aware helpers in `database/db.py`
- 07-add-expense — the validation rules, the form layout, and the `_validate_amount` helper that this step reuses

## Routes
- `GET /expenses/<int:id>/edit` — fetch the row (404 if missing or owned by another user), render the form pre-filled with the row's current values — logged-in only (redirect to `/login` if not authenticated)
- `POST /expenses/<int:id>/edit` — fetch the row (404 if missing or owned by another user), validate input with the same rules as add, update the row in place, redirect to `/profile` on success, re-render the form with errors on failure — logged-in only

No new routes. The URL is the same shape as the existing Step 8 stub (`/expenses/<int:id>/edit`); only the implementation changes.

## Database changes
No database changes. The `expenses` table from Step 1 already has every column this feature needs. The DB-layer change in this step is a single new helper, `update_expense(user_id, expense_id, amount, category, date, description)`, that runs one parameterised `UPDATE` guarded by `user_id` so a user can never mutate another user's row even if they guess the id.

## Templates
- **Create:** `templates/edit_expense.html` — extends `base.html`, mirrors `add_expense.html` (same field order, same `.auth-error` + `.field-error` styling, same Cancel link), but the form action targets `url_for('edit_expense', id=expense.id)` and the submit button reads `Save changes`
- **Modify:** `templates/profile.html` — add an `Edit` link in the recent-transactions table that targets `url_for('edit_expense', id=row.id)` (or equivalent, depending on what the row loop variable is named). No layout changes. The link is a small text or icon link, not a primary button, to keep the table visually quiet.

## Form (UI)
The edit form is the add form, pre-filled. Specifically:

- Same single centered card, same max-width, same four fields in the same order: Amount, Category, Date, Description.
- On `GET`, the form values come from the row, not from `_empty_form_values`. Amount is rendered as a plain decimal string (e.g. `45.00`), date as `YYYY-MM-DD`, category as the matching `<option selected>`, description as the row's value (empty string when `NULL`).
- On `POST` validation error, the round-tripped values come from the submitted form (same as Step 7), not from the row, so the user keeps their in-progress typing on a failed submit.
- Submit button label is `Save changes`. Cancel link returns to `url_for('profile')`.
- A small header line above the form (or in `.auth-subtitle`) reads `Editing expense from <date>` or similar, so the user can confirm they are editing the right row. This is a small UX nicety, not a requirement.

## Validation rules
Identical to Step 7 (add). The same `_validate_amount` helper is reused; the category, date, and description checks are duplicated as a small private helper in `app.py` (e.g. `_validate_expense_form(...)`) so both routes share one definition and the rules cannot drift.

- `amount` — required; must parse as `float`; must be `> 0`; round to 2 decimal places on update
- `category` — required; must be one of the seven canonical values
- `date` — required; must parse as `YYYY-MM-DD`; must not be in the future
- `description` — optional; strip whitespace; treat empty string as `None` so the column is `NULL` rather than `""`
- If any rule fails, re-render the form with a single error banner + a `.field-error` highlight on the offending field
- `user_id` is never accepted from the form — it is always read from `session['user_id']` and used as the `WHERE user_id = ?` guard on the UPDATE
- `expense_id` is never accepted from the form body — it comes from the URL, and the row must exist and belong to the logged-in user (404 otherwise)

## Ownership and 404 handling
The route must not leak the existence of another user's row. Two cases, both `abort(404)`:

- The id does not exist in `expenses` at all → 404
- The id exists but its `user_id` does not match `session['user_id']` → 404 (not 403, to avoid confirming the row's existence)

This check happens on both `GET` and `POST`, before any form read, so a logged-in user can never reach the form for a row they do not own.

## Redirect / success
On a successful update, redirect (HTTP 302) to `url_for('profile')`. The change will be visible in the recent-transactions table because the row's `date` and `amount` are read live from the DB. No flash message is required at this step — the redirect is the feedback.

## Files to change
- `app.py` — replace the `edit_expense` stub with a real `GET` + `POST` handler; add a `_validate_expense_form` helper (or similar) that both `add_expense` and `edit_expense` call, refactor the add route to use it without changing its behaviour
- `database/db.py` — add `update_expense(user_id, expense_id, amount, category, date, description)`; add `get_expense_by_id(user_id, expense_id)` for the GET branch
- `templates/profile.html` — add the `Edit` link to each row in the recent-transactions table

## Files to create
- `templates/edit_expense.html` — the edit form (mirrors `add_expense.html`)
- `static/css/edit-expense.css` — page-specific styles. Most styles are already on `.auth-section` / `.auth-card`; the new file is small and only adds edit-specific tweaks (e.g. the header subtitle styling). Follows the same CSS-variable convention. No hex values.

## New dependencies
No new dependencies. No new pip packages, no new JS packages, no CDN scripts. The date input uses the native HTML5 control, same as Step 7.

## New helpers in `database/db.py`
- `get_expense_by_id(user_id, expense_id)` — return the `expenses` row whose `id = ?` AND `user_id = ?`, or `None`. Used by the edit route to fetch the row for the GET branch and to gate the POST branch on ownership. Single parameterised `SELECT * FROM expenses WHERE id = ? AND user_id = ?`.
- `update_expense(user_id, expense_id, amount, category, date, description)` — run `UPDATE expenses SET amount = ?, category = ?, date = ?, description = ? WHERE id = ? AND user_id = ?`, commit, and return the number of affected rows (so the route can confirm the update actually hit a row the user owns). All values are passed as parameters — no f-strings in SQL. `description` may be `None`. Does not touch `created_at` — that column records the original insert time and is intentionally immutable.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()` only
- Parameterised queries only — `?` placeholders for every value, including the user_id guard on both `SELECT` and `UPDATE`
- Passwords are not touched at this step; auth state is read from `session` only
- Use CSS variables — never hardcode hex values (the new `edit-expense.css` must follow the same `--var-name` pattern already in `style.css` and `add-expense.css`)
- All templates extend `base.html` — no exceptions
- DB logic must reside in `database/db.py` — `app.py` only reads the form, calls helpers, renders
- Route functions have one responsibility only — fetch row, validate input, call helper, redirect or re-render
- Use `abort(404)` for missing rows and rows the user does not own — do not return a plain string, do not redirect, do not leak the row's existence with a 403
- The Step 7 validation logic must be reused (via the shared helper), not copy-pasted into the edit route. After refactor, `add_expense` and `edit_expense` must share one definition of "what counts as a valid expense"
- Use `url_for('edit_expense', id=expense.id)` for the form action and `url_for('profile')` for the cancel link — never hardcode paths
- The route must remain auth-gated: redirect to `/login` if `session.get("user_id")` is missing on both `GET` and `POST`
- `user_id` for the UPDATE guard must come from `session['user_id']` — never from the form
- The `created_at` column is intentionally never written to by the application — the UPDATE statement must not list it
- Date input is the native `<input type="date">`; do not bring in a date picker library
- Vanilla JS only — no React, no jQuery, no framework, no new `<script>` tags beyond what `base.html` already loads
- The form should keep the user's submitted values on a validation error (round-trip). This is rendered server-side from the variables passed back to the template.

## Definition of done
- [ ] `GET /expenses/<id>/edit` (logged in, owns the row) renders the form pre-filled with the row's amount, category, date, description
- [ ] `GET /expenses/<id>/edit` (logged in, row belongs to another user) returns 404
- [ ] `GET /expenses/<id>/edit` (logged in, id does not exist) returns 404
- [ ] `GET /expenses/<id>/edit` (not logged in) redirects to `/login`
- [ ] `POST /expenses/<id>/edit` with valid input updates the row in place, commits, and redirects to `/profile`
- [ ] After a successful edit, the row's new values appear in the recent-transactions table on `/profile` without a manual refresh
- [ ] After a successful edit, the row's `created_at` is unchanged
- [ ] The `UPDATE` statement's `WHERE` clause includes `user_id = ?` — a user can never mutate another user's row even if they POST to the right id
- [ ] An empty `amount` re-renders the form with an error and does not update
- [ ] A non-numeric `amount` re-renders the form with an error and does not update
- [ ] An `amount` of `0` or negative re-renders the form with an error and does not update
- [ ] A missing `category` re-renders the form with an error and does not update
- [ ] A `category` not in the seven canonical values re-renders the form with an error and does not update
- [ ] A missing `date` re-renders the form with an error and does not update
- [ ] A malformed `date` re-renders the form with an error and does not update
- [ ] A future `date` re-renders the form with an error and does not update
- [ ] A blank `description` is stored as `NULL`, not the empty string
- [ ] On any validation error, the previously submitted valid fields keep their values in the re-rendered form (not the row's original values)
- [ ] The Category dropdown contains exactly the seven values in the same order as Step 7
- [ ] The Cancel link returns to `/profile` without updating
- [ ] `POST /expenses/<id>/edit` (not logged in) redirects to `/login` and does not update
- [ ] `POST /expenses/<id>/edit` (logged in, row belongs to another user) returns 404 and does not update
- [ ] No SQL in `app.py` — all reads and writes go through `database/db.py`
- [ ] All SQL uses `?` placeholders (no f-strings, no string concatenation)
- [ ] The new `update_expense` and `get_expense_by_id` helpers are added to `database/db.py`
- [ ] The Step 7 add route is refactored to share the validation helper with the edit route (no duplicated validation logic)
- [ ] The new CSS file is page-specific (`static/css/edit-expense.css`) and uses only CSS variables from `style.css`
- [ ] The new template extends `base.html`
- [ ] Each row in the recent-transactions table on `/profile` has a working `Edit` link to `url_for('edit_expense', id=row.id)` (no `href="#"`, no hardcoded path)
- [ ] `pytest` still passes (no regressions in the existing test suite, including Step 7's add-expense tests)
