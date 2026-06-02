# Spec: Add Expense

## Overview
Let a logged-in user record a new expense from a dedicated `/expenses/add` page. The form accepts an amount, category, date, and optional description, validates the input on the server, persists the row to the existing `expenses` table, and redirects the user to `/profile` so the new entry is immediately reflected in the dashboard. Until now the only way to get rows into `expenses` was `seed_db()`; this step opens the real data-entry path that every later expense route (edit, delete, list) depends on. The new page replaces the Step 7 stub (`return "Add expense — coming in Step 7"`) and the Add Expense affordance already present on `/profile` is wired to it.

## Depends on
- 01-database-setup — `expenses` table must exist with `(user_id, amount, category, date, description)`
- 02-registration — accounts must be creatable
- 03-login-and-logout — `session['user_id']` must be set when reaching `/expenses/add`
- 04-profile-page-design — the "Add expense" entry point on the profile must already exist
- 05-backend-route-for-profile-page — `/profile` must read real rows so the redirect-after-add has a visible effect
- 06-date-filter-for-profile-page — optional but helpful: the new expense's `date` is rendered correctly by the date-aware helpers in `database/db.py`

## Routes
- `GET /expenses/add` — render the empty add-expense form — logged-in only (redirect to `/login` if not authenticated)
- `POST /expenses/add` — validate input, insert a row into `expenses` for the logged-in user, redirect to `/profile` on success, re-render the form with errors on failure — logged-in only

No new routes for "list all expenses" — the profile page's recent-transactions table continues to be the list view at this stage.

## Categories
The category field is a fixed `<select>` populated from the same canonical list `seed_db()` uses, in the same order. New categories cannot be created by the user at this step.

- `Food`
- `Transport`
- `Bills`
- `Health`
- `Entertainment`
- `Shopping`
- `Other`

## Database changes
No database changes. The `expenses` table created in Step 1 already has every column this feature needs:

- `user_id` (FK to `users.id`) — populated from `session['user_id']`
- `amount` (REAL, NOT NULL) — populated from form
- `category` (TEXT, NOT NULL) — populated from form (one of the seven preset values)
- `date` (TEXT, NOT NULL, `YYYY-MM-DD`) — populated from form
- `description` (TEXT, nullable) — populated from form (may be NULL or empty)
- `created_at` (TEXT, default `datetime('now')`) — auto-populated by the SQLite default

The DB-layer change in this step is a single new helper, `add_expense(...)`, that runs one parameterized `INSERT`. No migrations, no new tables, no new columns.

## Templates
- **Create:** `templates/add_expense.html` — extends `base.html`, contains the form (amount, category, date, description) and error rendering
- **Modify:** `templates/profile.html` — the existing "Add expense" link/button on the profile page should already target `url_for('add_expense')`; confirm and fix if it currently points at a hardcoded path or `#`. No other layout changes.

## Form (UI)
- A single centered card on the page, narrower than the auth pages (max-width ~480px) so it reads as a focused task.
- Four fields, in this order:
  1. `Amount` — `<input type="number" name="amount" step="0.01" min="0.01" required>`. HTML5 number input is the only client-side validation; the server re-validates.
  2. `Category` — `<select name="category" required>` populated with the seven categories above.
  3. `Date` — `<input type="date" name="date" required>`. Pre-filled with today's date on first render so the common case is "open the page, type an amount, hit save".
  4. `Description` — `<textarea name="description" rows="3" maxlength="200">`. Optional.
- A single primary submit button labelled `Add expense`.
- A `Cancel` link back to `url_for('profile')`.
- Server-side errors render as a single banner at the top of the card (same `.auth-error` style already used by login/register), with the field that failed the validation highlighted via a small `.field-error` class. On error, all valid fields keep their submitted values (round-trip) so the user does not have to re-type them.

## Validation rules
Validation lives in the route (or in a small private helper in `app.py`) — no business logic in the template.

- `amount` — required; must parse as `float`; must be `> 0`; round to 2 decimal places on insert (stored as the parsed float, not a formatted string)
- `category` — required; must be one of the seven canonical values (reject any other string)
- `date` — required; must parse as `YYYY-MM-DD`; must not be in the future (a typo'd future date is a real footgun)
- `description` — optional; strip whitespace; treat empty string as `None` so the column is `NULL` rather than `""`
- If any rule fails, the route re-renders the form with a list of error messages — the form does not silently submit
- `user_id` is never accepted from the form — it is always read from `session['user_id']`

## Redirect / success
On a successful insert, redirect (HTTP 302) to `url_for('profile')`. The new row will be visible in the recent-transactions table because Step 5's `get_expenses_for_user` already orders by `date DESC, id DESC` and Step 6's helpers honour the same ordering under the active filter. No flash message is required at this step — the redirect is the feedback.

## Files to change
- `app.py` — replace the `add_expense` stub with a real `GET` + `POST` handler; add the small validation helper
- `database/db.py` — add the `add_expense(user_id, amount, category, date, description)` helper
- `templates/profile.html` — confirm the "Add expense" affordance points at `url_for('add_expense')`; fix it if it doesn't

## Files to create
- `templates/add_expense.html` — the form
- `static/css/add-expense.css` — page-specific styles for the form (card width, field-error highlight, button row). Follows the same CSS-variable convention as the other page-specific stylesheets. No hex values.

## New dependencies
No new dependencies. No new pip packages, no new JS packages, no CDN scripts. The date input uses the native HTML5 control.

## New helper in `database/db.py`
- `add_expense(user_id, amount, category, date, description)` — run a single `INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)`, commit, and return the new row's `id` (or `cursor.lastrowid`) so the route can use it if it ever needs to. All values are passed as parameters — no f-strings in SQL. `description` is allowed to be `None`; the helper should accept `None` and let SQLite store it as `NULL`.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()` only
- Parameterised queries only — `?` placeholders for every value, including the user_id and the date
- Passwords are not touched at this step; auth state is read from `session` only
- Use CSS variables — never hardcode hex values (the new `add-expense.css` must follow the same `--var-name` pattern already in `style.css`)
- All templates extend `base.html` — no exceptions
- DB logic must reside in `database/db.py` — `app.py` only reads the form, calls helpers, renders
- Route functions have one responsibility only — parse form, call helper, redirect or re-render
- Use `abort()` for HTTP errors when applicable; the form validation flow uses re-render, not `abort()`
- Use `url_for('add_expense')` for the form action and `url_for('profile')` for the cancel link — never hardcode paths
- The route must remain auth-gated: redirect to `/login` if `session.get("user_id")` is missing on both `GET` and `POST`
- `user_id` for the new row must come from `session['user_id']` — never from the form
- Date input is the native `<input type="date">`; do not bring in a date picker library
- Vanilla JS only — no React, no jQuery, no framework, no new `<script>` tags beyond what `base.html` already loads
- The form should keep the user's submitted values on a validation error (round-trip). This is rendered server-side from the variables passed back to the template.

## Definition of done
- [ ] `GET /expenses/add` (logged in) renders the form with amount, category, date (pre-filled with today), description
- [ ] `GET /expenses/add` (not logged in) redirects to `/login`
- [ ] `POST /expenses/add` with valid input inserts a row, commits, and redirects to `/profile`
- [ ] After a successful add, the new expense appears in the recent-transactions table on `/profile` without a manual refresh
- [ ] The new row's `user_id` is the logged-in user's id (never the form's hidden field)
- [ ] The new row's `created_at` is auto-populated by SQLite's `datetime('now')` default
- [ ] An empty `amount` re-renders the form with an error and does not insert
- [ ] A non-numeric `amount` re-renders the form with an error and does not insert
- [ ] An `amount` of `0` or negative re-renders the form with an error and does not insert
- [ ] A missing `category` re-renders the form with an error and does not insert
- [ ] A `category` not in the seven canonical values re-renders the form with an error and does not insert
- [ ] A missing `date` re-renders the form with an error and does not insert
- [ ] A malformed `date` re-renders the form with an error and does not insert
- [ ] A future `date` re-renders the form with an error and does not insert
- [ ] A blank `description` is stored as `NULL`, not the empty string
- [ ] On any validation error, the previously submitted valid fields keep their values in the re-rendered form
- [ ] The Category dropdown contains exactly the seven values in the order listed in §Categories
- [ ] The Cancel link returns to `/profile` without inserting
- [ ] `POST /expenses/add` (not logged in) redirects to `/login` and does not insert
- [ ] No SQL in `app.py` — all inserts go through `database/db.py`
- [ ] All SQL uses `?` placeholders (no f-strings, no string concatenation)
- [ ] The new CSS file is page-specific (`static/css/add-expense.css`) and uses only CSS variables from `style.css`
- [ ] The new template extends `base.html`
- [ ] The Add-expense entry point on `/profile` is a real link to `url_for('add_expense')` (no `href="#"`, no hardcoded path)
- [ ] `pytest` still passes (no regressions in the existing test suite)
