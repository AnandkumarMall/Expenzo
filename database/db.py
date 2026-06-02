import sqlite3
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta

DATABASE = 'expense_tracker.db'

# Canonical list of expense categories, in the order the form dropdown and
# seed data both use. Keep this as the single source of truth — the form
# iterates over it and seed_db() references it so the two can never drift.
EXPENSE_CATEGORIES = [
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
]


def get_db():
    """Get a database connection with foreign keys enabled and row factory."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def _date_clause(date_from, date_to):
    """Return (sql_fragment, params_tuple) for an optional inclusive date range.

    Returns ("", ()) when no filter is active. The fragment is safe to splice
    into a WHERE clause as `... AND date BETWEEN ? AND ?`. Both bounds are
    inclusive on the `expenses.date` column (TEXT, `YYYY-MM-DD`).
    """
    if date_from and date_to:
        return " AND date BETWEEN ? AND ?", (date_from, date_to)
    return "", ()


def get_user_by_email(email):
    """Fetch a user record by email. Returns a sqlite3.Row or None."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        return cursor.fetchone()


def get_user_by_id(user_id):
    """Fetch a user record by primary key. Returns a sqlite3.Row or None."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        return cursor.fetchone()


def get_expenses_for_user(user_id, limit=5, date_from=None, date_to=None):
    """Return the most recent N expenses for a user, ordered by date DESC, id DESC.

    If `date_from` and `date_to` are both provided (as ISO `YYYY-MM-DD` strings),
    the result is limited to expenses whose `date` falls inclusively in that range.
    The `id` column is included so callers can build per-row action links
    (e.g. /expenses/<id>/edit) without a second round-trip.
    """
    clause, params = _date_clause(date_from, date_to)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, date, category, description, amount FROM expenses "
            "WHERE user_id = ?" + clause + " ORDER BY date DESC, id DESC LIMIT ?",
            (user_id, *params, limit),
        )
        return cursor.fetchall()


def count_expenses_for_user(user_id, date_from=None, date_to=None):
    """Return the number of expenses for a user as an int.

    If `date_from` and `date_to` are both provided, the count is limited to
    expenses whose `date` falls inclusively in that range.
    """
    clause, params = _date_clause(date_from, date_to)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM expenses WHERE user_id = ?" + clause,
            (user_id, *params),
        )
        return int(cursor.fetchone()[0])


def get_total_spent(user_id, date_from=None, date_to=None):
    """Return the SUM(amount) for a user's expenses as a float. Returns 0.0 if no expenses.

    If `date_from` and `date_to` are both provided, the sum is limited to
    expenses whose `date` falls inclusively in that range.
    """
    clause, params = _date_clause(date_from, date_to)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE user_id = ?" + clause,
            (user_id, *params),
        )
        return float(cursor.fetchone()[0])


def get_top_category(user_id, date_from=None, date_to=None):
    """Return the category name with the highest total spend, or None if no expenses.

    If `date_from` and `date_to` are both provided, the ranking is limited to
    expenses whose `date` falls inclusively in that range.
    """
    clause, params = _date_clause(date_from, date_to)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT category FROM expenses WHERE user_id = ?"
            + clause
            + " GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1",
            (user_id, *params),
        )
        row = cursor.fetchone()
        return row[0] if row else None


def get_category_breakdown(user_id, date_from=None, date_to=None):
    """Return a list of (category, total_amount, percentage) tuples for the user.

    Ordered by total amount descending. Percentages are integers that sum to
    exactly 100 for any non-zero grand total, using largest-remainder rounding.
    Returns an empty list if the user has no expenses.

    If `date_from` and `date_to` are both provided, the breakdown is limited to
    expenses whose `date` falls inclusively in that range, and percentages are
    computed against the in-range grand total so they always sum to 100.
    """
    clause, params = _date_clause(date_from, date_to)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT category, SUM(amount) AS total FROM expenses "
            "WHERE user_id = ?" + clause + " GROUP BY category ORDER BY total DESC",
            (user_id, *params),
        )
        rows = cursor.fetchall()

    if not rows:
        return []

    grand_total = sum(row["total"] for row in rows)
    if grand_total == 0:
        return []

    # Compute raw percentages and floored percentages.
    raw = [(row["category"], row["total"], (row["total"] / grand_total) * 100)
           for row in rows]
    floored = [(cat, amt, int(raw_pct), raw_pct - int(raw_pct))
               for cat, amt, raw_pct in raw]
    floor_sum = sum(item[2] for item in floored)
    remainder = 100 - floor_sum

    # Sort by fractional part descending to decide who gets the extra points.
    # Stable sort preserves the existing (total DESC) order for ties.
    floored.sort(key=lambda item: item[3], reverse=True)

    breakdown = []
    for idx, (cat, amt, floor_pct, _frac) in enumerate(floored):
        pct = floor_pct + (1 if idx < remainder else 0)
        breakdown.append((cat, amt, pct))

    # Restore the original total-DESC order.
    totals_index = {row["category"]: idx for idx, row in enumerate(rows)}
    breakdown.sort(key=lambda item: totals_index[item[0]])
    return breakdown


def add_expense(user_id, amount, category, date, description):
    """Insert a new expense row for the given user. Returns the new row's id.

    `description` may be None — SQLite binds Python None to NULL via the `?`
    placeholder, and the column is nullable. All values are parameterised.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, date, description),
        )
        conn.commit()
        return cursor.lastrowid


def get_expense_by_id(user_id, expense_id):
    """Return the expenses row whose id AND user_id match, or None.

    Used by the edit route to fetch the row for GET and to gate POST on
    ownership in a single round-trip. A user querying another user's id
    gets None — the route treats that as 404. All values are parameterised.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM expenses WHERE id = ? AND user_id = ?",
            (expense_id, user_id),
        )
        return cursor.fetchone()


def update_expense(user_id, expense_id, amount, category, date, description):
    """UPDATE one row in place, guarded by user_id.

    Does not touch created_at — that column records the original insert
    time and is intentionally immutable. The route has already verified
    ownership via get_expense_by_id and treats a missing row as 404
    before reaching this helper, so the rowcount is not surfaced. A TOCTOU
    window between the SELECT and the UPDATE is bounded — a successful
    delete between the two would simply affect 0 rows, which the route
    cannot observe today. The Step-9 delete route should be reviewed for
    this race when it is added.
    `description` may be None. All values are parameterised.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE expenses SET amount = ?, category = ?, date = ?, "
            "description = ? WHERE id = ? AND user_id = ?",
            (amount, category, date, description, expense_id, user_id),
        )
        conn.commit()


def delete_expense(user_id, expense_id):
    """DELETE one row in place, guarded by user_id.

    Returns the rowcount so callers can distinguish a successful delete
    (1) from a no-op (0). The route's pre-flight get_expense_by_id makes
    a 0-rowcount result unreachable from /expenses/<id>/delete today, but
    the helper still surfaces it as a documented contract for future
    callers (e.g. a bulk-delete admin tool). All values are parameterised.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM expenses WHERE id = ? AND user_id = ?",
            (expense_id, user_id),
        )
        conn.commit()
        return cursor.rowcount


def init_db():
    """Initialize database tables - safe to run multiple times."""
    with get_db() as conn:
        cursor = conn.cursor()

        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        ''')

        # Expenses table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                date TEXT NOT NULL,
                description TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')

        conn.commit()


def seed_db():
    """Seed database with demo data - only runs if no users exist."""
    with get_db() as conn:
        cursor = conn.cursor()

        # Check if users already exist
        cursor.execute('SELECT COUNT(*) FROM users')
        if cursor.fetchone()[0] > 0:
            return  # Already seeded

        # Create demo user
        demo_password_hash = generate_password_hash('demo123')
        cursor.execute('''
            INSERT INTO users (name, email, password_hash)
            VALUES (?, ?, ?)
        ''', ('Demo User', 'demo@spendly.com', demo_password_hash))

        user_id = cursor.lastrowid

        # Define expense categories (from spec)
        categories = EXPENSE_CATEGORIES

        # Generate 8 sample expenses across current month
        base_date = datetime.now().date()
        expenses_data = [
            # Spread across different days and categories
            (user_id, 12.50, 'Food', (base_date - timedelta(days=2)).isoformat(), 'Coffee and pastry'),
            (user_id, 45.00, 'Transport', (base_date - timedelta(days=5)).isoformat(), 'Gas refill'),
            (user_id, 89.99, 'Shopping', (base_date - timedelta(days=3)).isoformat(), 'New shirt'),
            (user_id, 120.00, 'Bills', (base_date - timedelta(days=10)).isoformat(), 'Electricity bill'),
            (user_id, 25.00, 'Health', (base_date - timedelta(days=7)).isoformat(), 'Pharmacy'),
            (user_id, 30.00, 'Entertainment', (base_date - timedelta(days=1)).isoformat(), 'Movie tickets'),
            (user_id, 15.75, 'Food', (base_date - timedelta(days=4)).isoformat(), 'Lunch'),
            (user_id, 65.00, 'Shopping', (base_date - timedelta(days=8)).isoformat(), 'Groceries'),
        ]

        cursor.executemany('''
            INSERT INTO expenses (user_id, amount, category, date, description)
            VALUES (?, ?, ?, ?, ?)
        ''', expenses_data)

        conn.commit()
