"""Shared pytest fixtures for Spendly tests.

These fixtures provide:
- An isolated SQLite database per test (via a tmp file + monkeypatch of DATABASE).
- A Flask app wired up against the isolated DB.
- A Flask test client.
- A pre-registered, pre-logged-in test client.
- A helper for seeding expenses with a known date distribution.
"""

import os
import sys
import pytest
import datetime

# Make the project root importable when pytest is invoked from anywhere.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Import app and database after adjusting sys.path.
import app as app_module  # noqa: E402
import database.db as db_module  # noqa: E402

from werkzeug.security import generate_password_hash  # noqa: E402


# ---------------------------------------------------------------------------
# Constants used across the test suite. Today is "frozen" at 2026-06-01 so the
# preset windows (this_month, last_month, last_3_months, last_6_months) are
# deterministic regardless of when the tests are executed.
# ---------------------------------------------------------------------------
FROZEN_TODAY = datetime.date(2026, 6, 1)


@pytest.fixture
def frozen_today(monkeypatch):
    """Freeze the app's notion of "today" to FROZEN_TODAY.

    The spec's presets are computed against the server's "today" so we need a
    deterministic anchor to assert window boundaries reliably. We patch
    ``app._today`` (a module-level helper) rather than ``datetime.date.today``
    directly, because ``datetime.date`` is a C-implemented immutable type that
    does not allow attribute assignment.
    """
    def _fake_today():
        return FROZEN_TODAY

    monkeypatch.setattr(app_module, "_today", _fake_today)
    return FROZEN_TODAY


@pytest.fixture
def app(tmp_path, frozen_today, monkeypatch):
    """Create a Flask app backed by an isolated temporary SQLite database."""
    db_path = tmp_path / "test_expense_tracker.db"
    monkeypatch.setattr(db_module, "DATABASE", str(db_path))
    # Re-init the app's reference to the database by calling init_db which uses get_db().
    # (init_db() uses db_module.DATABASE via get_db()).
    db_module.init_db()
    db_module.seed_db()
    # Force a fresh request context so any cached app config is reset.
    app_module.app.config.update(TESTING=True, SECRET_KEY="test-secret")
    return app_module.app


@pytest.fixture
def client(app):
    """A Flask test client bound to the isolated app."""
    return app.test_client()


@pytest.fixture
def registered_user(app):
    """Register a fresh test user and return its row."""
    with app.app_context():
        conn = db_module.get_db()
        cursor = conn.cursor()
        password_hash = generate_password_hash("test-password-123")
        cursor.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Test User", "testuser@example.com", password_hash),
        )
        conn.commit()
        user_id = cursor.lastrowid
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user_row = cursor.fetchone()
    return user_row


@pytest.fixture
def logged_in_client(app, client, registered_user):
    """A Flask test client that is already logged in as the registered user."""
    with client.session_transaction() as sess:
        sess["user_id"] = registered_user["id"]
    return client


@pytest.fixture
def known_expenses(app, registered_user):
    """Seed a deterministic, spread-out set of expenses for the test user.

    Inserts one expense on the FIRST of each month for the previous 12 months
    relative to FROZEN_TODAY (2026-06-01). The first-of-month date is chosen
    so that the current-month expense is always inside the ``this_month`` /
    ``last_3_months`` / ``last_6_months`` windows regardless of the day of
    the month FROZEN_TODAY falls on.

    Amounts are 10..21 so totals are easy to reason about. The category is
    ``Cat-<month>`` so per-month assertions don't collide.
    """
    today = FROZEN_TODAY
    user_id = registered_user["id"]
    rows = []
    with app.app_context():
        conn = db_module.get_db()
        cursor = conn.cursor()
        for offset in range(12):
            # Walk back month by month from today.
            year = today.year
            month = today.month - offset
            while month <= 0:
                month += 12
                year -= 1
            d = datetime.date(year, month, 1)
            amount = float(10 + offset)  # 10..21
            category = f"Cat-{month:02d}"
            cursor.execute(
                "INSERT INTO expenses (user_id, amount, category, date, description) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, amount, category, d.isoformat(), f"exp-{offset}"),
            )
            rows.append({
                "date": d.isoformat(),
                "amount": amount,
                "category": category,
            })
        conn.commit()
    return rows


# ---------------------------------------------------------------------------
# DB-direct helper used by DB-helper unit tests.
# ---------------------------------------------------------------------------
@pytest.fixture
def isolated_db(tmp_path, monkeypatch, frozen_today):
    """Provide a freshly initialised DB module that the test can poke directly."""
    db_path = tmp_path / "unit_expense_tracker.db"
    monkeypatch.setattr(db_module, "DATABASE", str(db_path))
    db_module.init_db()
    # Insert a single user we can attach expenses to.
    with db_module.get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Unit User", "unituser@example.com", "x"),
        )
        user_id = cursor.lastrowid
    return {"user_id": user_id, "db_path": str(db_path)}
