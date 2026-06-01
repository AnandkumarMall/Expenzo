# Spec: Backend Route for Profile Page

## Overview
Replace the hardcoded data in the `/profile` route with real database queries so the profile page reflects the actual logged-in user. The existing template (`templates/profile.html`, built in Step 4) already defines the four sections — user info, summary stats, recent transactions, and category breakdown — and the route is already auth-gated. This step supplies the missing data layer: fetch the user record, aggregate their expenses into totals, compute the top category, and return the recent transactions and per-category breakdown. No template or styling changes are expected — only the data source moves from in-memory dicts to SQL.

## Depends on
- 01-database-setup — `users` and `expenses` tables must exist (already in `database/db.py`)
- 02-registration — user accounts must be creatable
- 03-login-and-logout — `session['user_id']` must be set when reaching `/profile`
- 04-profile-page-design — `templates/profile.html` must exist with the four sections wired up; the route must already redirect unauthenticated users to `/login`

## Routes
- `GET /profile` — render the profile page using real data for the logged-in user — logged-in only (redirect to `/login` if not authenticated)

No new routes are added in this step. `/profile` already exists; only its body changes.

## Database changes
No database changes. The `users` and `expenses` tables created in Step 1 are sufficient. All required data is already stored:

- `users`: `id`, `name`, `email`, `created_at` (for avatar, name, email, member-since)
- `expenses`: `user_id`, `amount`, `category`, `date`, `description` (for totals, top category, recent transactions, category breakdown)

## Templates
- **Modify:** none — `templates/profile.html` stays as-is. It already iterates over `transactions`, `category_totals`, and reads `user` / `stats` by name. The shape of the context variables this step produces must match exactly what the template expects (see "Context contract" below).

## Context contract
The route must pass the following context to `profile.html`. Field names and types are dictated by the existing template — do not rename them.

- `user` (dict): `name` (str), `email` (str), `member_since` (str, human-readable like `"January 2024"`)
- `stats` (dict): `total_spent` (str, formatted as `₹<amount>` with thousands separator), `transaction_count` (int), `top_category` (str or `"—"` if no expenses)
- `transactions` (list of dicts, newest first): each item has `date` (str, `YYYY-MM-DD`), `desc` (str), `cat` (str), `amt` (int|float) — used directly by the template as `{{ tx.amt }}`, so numeric is fine (the template prepends the `₹` glyph)
- `category_totals` (list of dicts, descending by amount): each item has `cat` (str), `amt` (int|float), `pct` (int, 0–100, percentage of total spend)

## Files to change
- `app.py` — replace the hardcoded dicts in the `profile()` view with real queries
- `database/db.py` — add helper functions used by the route

## Files to create
No new files.

## New dependencies
No new dependencies.

## New helpers in `database/db.py`
Add (in addition to the existing `get_db`, `get_user_by_email`, `init_db`, `seed_db`):

- `get_user_by_id(user_id)` — fetch a single user row by primary key. Returns a `sqlite3.Row` or `None`.
- `get_expenses_for_user(user_id, limit=5)` — return the most recent N expenses for a user, ordered by `date DESC, id DESC`. Returns a list of `sqlite3.Row`.
- `get_total_spent(user_id)` — return `SUM(amount)` for the user as a float. Returns `0.0` when the user has no expenses.
- `get_top_category(user_id)` — return the category name with the highest total spend, or `None` if the user has no expenses.
- `get_category_breakdown(user_id)` — return a list of `(category, total_amount, percentage)` tuples for the user, ordered by `total_amount DESC`. Percentage is rounded to the nearest integer and the values for a single user must sum to 100% (largest-remainder rounding is acceptable; if the user has zero spend, return `[]`).

All helpers must use parameterized queries (`?` placeholders) and `get_db()` for their connection — never open a `sqlite3.connect()` directly inside a helper.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()` only
- Parameterised queries only — never f-strings in SQL
- Passwords handled only with `werkzeug.security` (no auth changes in this step)
- Use CSS variables — never hardcode hex values (no styling changes are expected, but if any CSS is touched, this rule still applies)
- All templates extend `base.html` (no change — the existing template already does)
- DB logic must reside in `database/db.py` — route functions only fetch and render
- Route functions have one responsibility only — fetch data, render template, done
- Use `abort()` for HTTP errors, not bare string returns
- Use `url_for()` for every internal link — never hardcode URLs
- The route must be auth-gated: redirect to `/login` if `session.get("user_id")` is missing
- `user_id` from the session must be passed to every helper, never hardcoded
- If a logged-in `user_id` no longer exists in the `users` table (e.g. account deleted), the route must clear the stale session and redirect to `/login` rather than crash
- "Total spent" must be formatted as a thousands-separated string with the `₹` prefix (e.g. `₹42,500`)
- "Member since" must be a human-readable month-and-year string (e.g. `"January 2024"`) — derive it from `users.created_at`, not hardcoded
- `category_totals` percentages must be rounded integers; the largest-remainder method is the simplest way to guarantee they sum to 100 when the user has at least one expense
- The `transactions` list must be newest-first and capped at the 5 most recent (matching what the existing template already renders)

## Definition of done
- [ ] Visiting `/profile` without being logged in still redirects to `/login`
- [ ] Logging in as `demo@spendly.com` (the seeded user) and visiting `/profile` shows the demo user's name and email — not the previously hardcoded "Arjun Mehta"
- [ ] `Total Spent` on the profile page equals the sum of the demo user's seeded expenses
- [ ] `Transactions` count matches the number of seeded expenses (8) for the demo user
- [ ] `Top Category` matches whichever seeded category has the highest total
- [ ] The recent-transactions table shows the demo user's actual expenses (newest first), not the previously hardcoded Starbucks/Uber/Amazon rows
- [ ] The category breakdown list shows the categories present in the demo user's expenses, with percentages that sum to 100
- [ ] Registering a brand-new user and visiting `/profile` shows that new user's name, email, and `Member since <current month/year>` — with empty/zero stats and an empty transactions list
- [ ] The route uses helper functions from `database/db.py` — no SQL appears in `app.py`
- [ ] All SQL uses `?` parameter placeholders
- [ ] `pytest` still passes (no test regressions; the route is exercised by the test client)
- [ ] Visiting `/profile` with a `user_id` in the session that no longer exists in the database redirects to `/login` without a 500

