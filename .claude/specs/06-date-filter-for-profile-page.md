# Spec: Date Filter for Profile Page

## Overview
Add a date-range filter to the `/profile` page so a user can scope their summary stats, category breakdown, and recent-transactions table t
o a specific period. By default the profile shows the user's lifetime data; the filter lets them narrow the view to "This Month", "Last Month", "Last 3 Months", "Last 6 Months", or a custom `from`/`to` range. The filter lives on the profile page itself (no new pages), the chosen range is reflected in the URL via query parameters, and the same SQL aggregation logic that powers the profile is reused — only the `WHERE` clause changes. This makes the existing dashboard useful for month-end review and budget tracking without reloading the page from scratch or inventing a new page.

## Depends on
- 01-database-setup — `users` and `expenses` tables must exist
- 02-registration — user accounts must be creatable
- 03-login-and-logout — `session['user_id']` must be set when reaching `/profile`
- 04-profile-page-design — `templates/profile.html` must exist with the four sections wired up
- 05-backend-route-for-profile-page — the route must already aggregate real data from `database/db.py` so the filter can extend those helpers

## Routes
- `GET /profile` — render the profile page, optionally filtered by a date range — logged-in only (redirect to `/login` if not authenticated)

No new routes are added. `/profile` is extended to read `?from=YYYY-MM-DD&to=YYYY-MM-DD` (and/or `?range=<preset>`) query parameters and pass the filter down to the DB helpers.

## Query parameter contract
The filter is a pure read — `GET` only, no POST handler. All parameters are optional. Unknown values are ignored (fall back to lifetime).

- `range` (str, optional) — one of `this_month`, `last_month`, `last_3_months`, `last_6_months`, `custom`. When set and not `custom`, it overrides `from`/`to`. When `custom`, both `from` and `to` must be present and valid.
- `from` (str, optional, `YYYY-MM-DD`) — inclusive lower bound on `expenses.date`. Combined with `to` for custom ranges.
- `to` (str, optional, `YYYY-MM-DD`) — inclusive upper bound on `expenses.date`. Combined with `from` for custom ranges.
- Invalid dates (malformed or `from > to`) are silently ignored — the page falls back to lifetime totals rather than 400ing. This keeps the URL shareable and the back button friendly.
- The current filter is reflected back into the rendered template so the form's `<select>` and date inputs can rehydrate, and so the "Showing X — Y" banner reads correctly.

## Preset definitions
Computed against the user's "today" (server time, `datetime.now().date()`):

- `this_month` — `from = first day of current month`, `to = today`
- `last_month` — `from = first day of previous month`, `to = last day of previous month`
- `last_3_months` — `from = first day of (current month − 2 months)`, `to = today`
- `last_6_months` — `from = first day of (current month − 5 months)`, `to = today`
- `custom` — `from` and `to` as provided (after validation)

## Database changes
No database changes. The existing `expenses.date` column (TEXT, `YYYY-MM-DD`, populated by seed and add-expense) is the filter target. All filtering is done with `WHERE date BETWEEN ? AND ?` against the existing index-less column — no migration, no new columns, no new tables.

## Templates
- **Modify:** `templates/profile.html` — add a filter bar above the four existing sections, add a "Showing X — Y" indicator, and update the page title only if no filter is active (otherwise append the range). The four existing sections (user info, stats, category breakdown, recent transactions) keep their layout; the data inside them changes with the filter.
- **Create:** `static/css/profile-filter.css` — styles for the filter bar (select, date inputs, "Apply" / "Reset" buttons, the active-range banner). Page-specific styles live in their own file, never inline.

## Filter bar (UI)
A single horizontal bar above the stats grid, containing:

1. A `<select name="range">` with the five preset options plus a hidden "Lifetime" option that is selected when no filter is active.
2. Two `<input type="date" name="from">` and `<input type="date" name="to">`, visible only when `range=custom` (toggled with a tiny inline script — vanilla JS only, no new dependencies).
3. An `Apply` submit button (GET form) and a `Reset` link that clears the query string and reloads `/profile` with no filter.
4. A small banner under the bar: `Showing <from> — <to> · <N> transactions` when a filter is active, hidden when lifetime.

The filter is a plain `<form method="get" action="{{ url_for('profile') }}">` — no JS required for the basic flow. The show/hide for the custom date inputs is the only JS.

## Files to change
- `app.py` — read `range` / `from` / `to` from `request.args`, validate, compute the effective `[from_date, to_date]`, pass to helpers, and pass the active filter to the template
- `database/db.py` — extend each aggregation helper to accept an optional `date_from` / `date_to` pair; when both are `None`, behaviour is identical to today
- `templates/profile.html` — add the filter bar markup, the active-range banner, and the `{% block head %}` link for the new CSS
- `static/css/profile.css` — minor adjustments only if needed for layout (no hex values, CSS variables only)
- `static/css/profile-filter.css` — new file, owns the filter-bar styling

## Files to create
- `static/css/profile-filter.css` — filter-bar styles
- `static/js/profile-filter.js` (optional, only if the show/hide for custom dates is moved out of `main.js`) — vanilla JS toggle for the custom date inputs

If the existing `static/js/main.js` is a reasonable home for a few lines of toggle logic, that file can absorb the change instead of creating a new one — the spec does not require a new JS file.

## New dependencies
No new dependencies. No new pip packages, no new JS packages, no CDN scripts.

## New / changed helpers in `database/db.py`
Each aggregation helper gains an optional `(date_from=None, date_to=None)` keyword argument. When both are `None`, the SQL is unchanged from today; when provided, an extra `AND date BETWEEN ? AND ?` clause is added to the `WHERE`. Filters are always `AND`ed — never string-interpolated.

- `get_expenses_for_user(user_id, limit=5, date_from=None, date_to=None)` — return the most recent N expenses within the range, ordered by `date DESC, id DESC`.
- `count_expenses_for_user(user_id, date_from=None, date_to=None)` — return the count of expenses in the range.
- `get_total_spent(user_id, date_from=None, date_to=None)` — return `SUM(amount)` in the range as a float. `0.0` when no expenses in range.
- `get_top_category(user_id, date_from=None, date_to=None)` — return the top category in the range, or `None` if no expenses in range.
- `get_category_breakdown(user_id, date_from=None, date_to=None)` — return the per-category breakdown limited to the range. Percentages are recomputed against the in-range total, not the lifetime total, so they always sum to 100 when the range has at least one expense.

A small private helper `_date_clause(date_from, date_to)` (or an inline pattern repeated per function) is acceptable — the spec does not require a new public helper, only that the SQL be parameterized.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()` only
- Parameterised queries only — `?` placeholders for both the user_id and the date bounds
- Passwords handled only with `werkzeug.security` (no auth changes in this step)
- Use CSS variables — never hardcode hex values (the new `profile-filter.css` must follow the same `--var-name` pattern already in `style.css`)
- All templates extend `base.html` (no change)
- DB logic must reside in `database/db.py` — route functions only parse query args, call helpers, render
- Route functions have one responsibility only — parse filter, fetch data, render template
- Use `abort()` for HTTP errors when applicable; for invalid date inputs the spec is explicit — fall back to lifetime, do not 400
- Use `url_for('profile')` for the form action — never hardcode `/profile`
- The route must remain auth-gated: redirect to `/login` if `session.get("user_id")` is missing
- The filter must not affect auth or the user-info card — name, email, and "Member since" are always lifetime
- The filter must be safe against bad input: malformed dates are ignored, `from > to` is ignored, unknown preset values are ignored
- Vanilla JS only for the custom-date show/hide — no React, no jQuery, no framework
- The filter bar must be a `<form method="get">` so the URL is shareable and the back button works

## Definition of done
- [ ] Visiting `/profile` (no query string) still shows lifetime totals — existing Step 5 behaviour is preserved
- [ ] Visiting `/profile?range=this_month` shows stats, breakdown, and transactions limited to the current month
- [ ] Visiting `/profile?range=last_month` shows stats, breakdown, and transactions limited to the previous calendar month (not "the last 30 days")
- [ ] Visiting `/profile?range=last_3_months` and `?range=last_6_months` produce the expected wider windows
- [ ] Visiting `/profile?range=custom&from=2025-01-01&to=2025-01-31` shows only January 2025 expenses
- [ ] Visiting `/profile?from=2025-01-01&to=2025-01-31` (no `range` param) is treated as a custom range and works the same
- [ ] Visiting `/profile?range=custom&from=garbage&to=2025-01-31` falls back to lifetime (no 500, no 400)
- [ ] Visiting `/profile?range=custom&from=2025-12-31&to=2025-01-01` (from > to) falls back to lifetime
- [ ] Visiting `/profile?range=banana` (unknown preset) falls back to lifetime
- [ ] The user-info card (name, email, member-since) is identical with or without a filter
- [ ] The filter bar's `<select>` and date inputs rehydrate to the active filter after a refresh
- [ ] The "Showing X — Y · N transactions" banner appears when a filter is active and is hidden for lifetime
- [ ] `Total Spent` equals `SUM(amount)` of expenses whose `date` falls inside the range
- [ ] `Transactions` count equals the number of expenses inside the range
- [ ] `Top Category` is the highest-spend category inside the range, or `—` if the range is empty
- [ ] The category-breakdown percentages sum to exactly 100 when the range has at least one expense (largest-remainder, as in Step 5)
- [ ] Clicking `Reset` returns to the unfiltered `/profile` view
- [ ] The filter is a `GET` form — no POST route is added, the URL is shareable
- [ ] All SQL uses `?` parameter placeholders (no f-strings in SQL, even for the date bounds)
- [ ] The route uses helper functions from `database/db.py` — no SQL appears in `app.py`
- [ ] Visiting `/profile` while not logged in still redirects to `/login`
- [ ] `pytest` still passes (no regressions in the existing test suite)
