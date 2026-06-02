"""Black-box test suite for Spendly spec 08 — Edit expense.

Derived from `.claude/specs/08-edit-expense.md` Definition of done. Tests
target the public HTTP interface (`GET` / `POST /expenses/<id>/edit`) and
the observable DB state via direct ``SELECT`` queries — never via
importing the route handlers or DB helpers under test.

The conftest freezes "today" at 2026-06-01 (FROZEN_TODAY) via the
``frozen_today`` fixture, so "date is in the future" assertions are
deterministic.
"""

import os
import re
import datetime

import pytest

import database.db as db_module
from database.db import EXPENSE_CATEGORIES
from werkzeug.security import generate_password_hash


# The conftest's FROZEN_TODAY value. Kept local so each assertion reads
# naturally beside the dates it compares against.
TODAY = datetime.date(2026, 6, 1)


# ---------------------------------------------------------------------------
# Helpers — pure HTML / DB inspection utilities.
# None of them know anything about the route implementation; they only know
# the shapes the spec describes (a form with named inputs, a select named
# "category" with seven options, a Cancel link, and an `expenses` table).
# ---------------------------------------------------------------------------

def _count_expenses_for_user(app, user_id):
    """Return the number of expense rows scoped to a single user."""
    with app.app_context():
        with db_module.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM expenses WHERE user_id = ?", (user_id,)
            )
            return int(cursor.fetchone()[0])


def _fetch_expense(app, expense_id):
    """Return the row with the given expense id (any user) or None."""
    with app.app_context():
        with db_module.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM expenses WHERE id = ?", (expense_id,)
            )
            return cursor.fetchone()


def _insert_expense(app, user_id, amount, category, date_str, description):
    """Insert an expense row directly via SQL and return its id.

    Bypasses the add-expense route so tests can set up known state
    without coupling to the add-expense code path.
    """
    with app.app_context():
        with db_module.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO expenses (user_id, amount, category, date, description) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, amount, category, date_str, description),
            )
            conn.commit()
            return cursor.lastrowid


def _input_value(html, name):
    """Return the value attribute of ``<input name="<name>" ...>`` or None."""
    pattern = r'<input[^>]*name="' + re.escape(name) + r'"[^>]*value="([^"]*)"'
    m = re.search(pattern, html)
    if m:
        return m.group(1)
    m = re.search(
        r'<input[^>]*value="([^"]*)"[^>]*name="' + re.escape(name) + r'"',
        html,
    )
    return m.group(1) if m else None


def _textarea_content(html, name):
    """Return the inner text of ``<textarea name="<name>">...</textarea>``."""
    pattern = (
        r'<textarea[^>]*name="' + re.escape(name) + r'"[^>]*>(.*?)</textarea>'
    )
    m = re.search(pattern, html, re.DOTALL)
    return m.group(1) if m else None


def _category_select_inner(html):
    """Return the inner HTML of ``<select name="category">`` or ''."""
    m = re.search(
        r'<select[^>]*name="category"[^>]*>(.*?)</select>', html, re.DOTALL
    )
    return m.group(1) if m else ""


def _category_options(html):
    """Return the list of non-empty option values inside the category select."""
    inner = _category_select_inner(html)
    values = re.findall(r'<option[^>]*value="([^"]*)"', inner)
    return [v for v in values if v != ""]


def _selected_category(html):
    """Return the value of the selected option inside ``<select name="category">``."""
    inner = _category_select_inner(html)
    m = re.search(
        r'<option[^>]*value="([^"]*)"[^>]*\bselected\b[^>]*>', inner
    )
    if m and m.group(1):
        return m.group(1)
    m = re.search(
        r'<option[^>]*\bselected\b[^>]*value="([^"]*)"[^>]*>', inner
    )
    if m and m.group(1):
        return m.group(1)
    return None


def _form_action(html):
    """Return the action attribute of the first <form>, or None."""
    m = re.search(r'<form[^>]*action="([^"]*)"', html)
    return m.group(1) if m else None


def _submit_button_text(html):
    """Return the text of the first <button type="submit">, or None."""
    m = re.search(r'<button[^>]*type="submit"[^>]*>(.*?)</button>', html, re.DOTALL)
    return m.group(1).strip() if m else None


def _has_link_to(html, target):
    """True if any anchor has ``href="<target>"`` (single or double quotes)."""
    return f'href="{target}"' in html or f"href='{target}'" in html


# ---------------------------------------------------------------------------
# Fixtures local to this test file. The conftest's `logged_in_client` only
# logs in as `registered_user`; for the ownership tests we need a second
# user we can log in as.
# ---------------------------------------------------------------------------

@pytest.fixture
def other_user(app):
    """Register a second user and return its row. Used by ownership tests."""
    with app.app_context():
        conn = db_module.get_db()
        cursor = conn.cursor()
        password_hash = generate_password_hash("other-password-123")
        cursor.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Other User", "other@example.com", password_hash),
        )
        conn.commit()
        user_id = cursor.lastrowid
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user_row = cursor.fetchone()
    return user_row


@pytest.fixture
def other_logged_in_client(app, client, other_user):
    """A Flask test client logged in as `other_user`."""
    with client.session_transaction() as sess:
        sess["user_id"] = other_user["id"]
    return client


@pytest.fixture
def owned_expense(app, registered_user):
    """Insert one expense owned by registered_user and return its id + data."""
    expense_id = _insert_expense(
        app, registered_user["id"],
        amount=42.50, category="Food", date_str="2026-05-15",
        description="Original description",
    )
    return {
        "id": expense_id,
        "amount": 42.50,
        "category": "Food",
        "date": "2026-05-15",
        "description": "Original description",
    }


# ---------------------------------------------------------------------------
# Section 1 — Auth guards (DoD: GET/POST unauthenticated → /login).
# ---------------------------------------------------------------------------

class TestAuthGuards:
    """The edit-expense route is auth-gated on both GET and POST."""

    def test_get_unauthenticated_redirects_to_login(self, client, owned_expense):
        """GET /expenses/<id>/edit (not logged in) → /login (DoD)."""
        resp = client.get(f"/expenses/{owned_expense['id']}/edit")
        assert resp.status_code == 302
        assert "/login" in resp.headers.get("Location", "")

    def test_post_unauthenticated_redirects_to_login(self, client, owned_expense):
        """POST /expenses/<id>/edit (not logged in) → /login (DoD)."""
        resp = client.post(
            f"/expenses/{owned_expense['id']}/edit",
            data={
                "amount": "99.99",
                "category": "Other",
                "date": TODAY.isoformat(),
                "description": "sneaky",
            },
        )
        assert resp.status_code == 302
        assert "/login" in resp.headers.get("Location", "")

    def test_post_unauthenticated_does_not_update(self, app, client, owned_expense):
        """POST /expenses/<id>/edit (not logged in) must NOT update the row (DoD)."""
        client.post(
            f"/expenses/{owned_expense['id']}/edit",
            data={
                "amount": "99.99",
                "category": "Other",
                "date": TODAY.isoformat(),
                "description": "sneaky",
            },
        )
        # Re-fetch and assert byte-for-byte unchanged.
        row = _fetch_expense(app, owned_expense["id"])
        assert row is not None
        assert abs(row["amount"] - owned_expense["amount"]) < 0.001
        assert row["category"] == owned_expense["category"]
        assert row["date"] == owned_expense["date"]
        assert row["description"] == owned_expense["description"]


# ---------------------------------------------------------------------------
# Section 2 — 404 for missing rows and other-user rows (DoD).
# ---------------------------------------------------------------------------

class TestOwnershipAnd404:
    """404 for missing rows AND for rows the user does not own (DoD)."""

    def test_get_missing_id_returns_404(self, logged_in_client):
        """GET a non-existent id → 404 (DoD)."""
        resp = logged_in_client.get("/expenses/99999/edit")
        assert resp.status_code == 404

    def test_post_missing_id_returns_404(self, logged_in_client):
        """POST to a non-existent id → 404 (DoD)."""
        resp = logged_in_client.post(
            "/expenses/99999/edit",
            data={
                "amount": "10.00",
                "category": "Food",
                "date": TODAY.isoformat(),
                "description": "",
            },
        )
        assert resp.status_code == 404

    def test_get_other_users_row_returns_404(
        self, app, other_logged_in_client, registered_user
    ):
        """GET a row owned by another user → 404 (DoD, not 403).

        The spec is explicit: a 404 (not 403) avoids leaking the row's
        existence. The test logs in as a different user and inspects a
        row owned by `registered_user`.
        """
        eid = _insert_expense(
            app, registered_user["id"],
            amount=10.0, category="Food", date_str="2026-05-01",
            description="not yours",
        )
        resp = other_logged_in_client.get(f"/expenses/{eid}/edit")
        assert resp.status_code == 404

    def test_post_other_users_row_returns_404_and_does_not_update(
        self, app, other_logged_in_client, registered_user
    ):
        """POST to a row owned by another user → 404 AND row unchanged (DoD)."""
        eid = _insert_expense(
            app, registered_user["id"],
            amount=10.0, category="Food", date_str="2026-05-01",
            description="not yours",
        )
        resp = other_logged_in_client.post(
            f"/expenses/{eid}/edit",
            data={
                "amount": "999.99",
                "category": "Bills",
                "date": "2026-05-02",
                "description": "hostile",
            },
        )
        assert resp.status_code == 404
        # And the row must be byte-for-byte unchanged.
        row = _fetch_expense(app, eid)
        assert row is not None
        assert abs(row["amount"] - 10.0) < 0.001
        assert row["category"] == "Food"
        assert row["description"] == "not yours"
        assert row["date"] == "2026-05-01"


# ---------------------------------------------------------------------------
# Section 3 — GET happy path (DoD: form pre-filled, categories in order,
# Cancel → /profile, extends base.html, Submit reads "Save changes",
# action points at edit URL).
# ---------------------------------------------------------------------------

class TestGetForm:
    """Logged-in GET /expenses/<id>/edit renders the form pre-filled."""

    def test_get_returns_200_with_form(self, logged_in_client, owned_expense):
        """GET returns 200 and renders the four form fields (DoD)."""
        resp = logged_in_client.get(f"/expenses/{owned_expense['id']}/edit")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert 'name="amount"' in body
        assert 'name="category"' in body
        assert 'name="date"' in body
        assert 'name="description"' in body

    def test_get_amount_prefilled_with_row_value(
        self, logged_in_client, owned_expense
    ):
        """Amount field is pre-filled with the row's amount (DoD).

        Spec §Form: "Amount is rendered as a plain decimal string
        (e.g. 45.00)". The fixture inserts 42.50, so the value attribute
        must read "42.50".
        """
        resp = logged_in_client.get(f"/expenses/{owned_expense['id']}/edit")
        body = resp.get_data(as_text=True)
        assert _input_value(body, "amount") == "42.50"

    def test_get_category_prefilled_with_row_value(
        self, logged_in_client, owned_expense
    ):
        """Category dropdown is pre-selected with the row's category (DoD)."""
        resp = logged_in_client.get(f"/expenses/{owned_expense['id']}/edit")
        body = resp.get_data(as_text=True)
        assert _selected_category(body) == "Food"

    def test_get_date_prefilled_with_row_value(
        self, logged_in_client, owned_expense
    ):
        """Date field is pre-filled with the row's date (DoD)."""
        resp = logged_in_client.get(f"/expenses/{owned_expense['id']}/edit")
        body = resp.get_data(as_text=True)
        assert _input_value(body, "date") == "2026-05-15"

    def test_get_description_prefilled_with_row_value(
        self, logged_in_client, owned_expense
    ):
        """Description textarea is pre-filled with the row's description (DoD)."""
        resp = logged_in_client.get(f"/expenses/{owned_expense['id']}/edit")
        body = resp.get_data(as_text=True)
        ta = _textarea_content(body, "description")
        assert ta is not None
        assert "Original description" in ta

    def test_get_description_prefilled_empty_when_null(
        self, app, logged_in_client, registered_user
    ):
        """Description textarea is empty when the row's description is NULL (DoD).

        Inserts a fresh row with description=None, then asserts the
        rendered <textarea> is empty.
        """
        eid = _insert_expense(
            app, registered_user["id"],
            amount=5.0, category="Other", date_str="2026-04-01",
            description=None,
        )
        resp = logged_in_client.get(f"/expenses/{eid}/edit")
        body = resp.get_data(as_text=True)
        ta = _textarea_content(body, "description")
        assert ta is not None
        assert ta.strip() == ""

    def test_get_category_dropdown_contains_canonical_values_in_order(
        self, logged_in_client, owned_expense
    ):
        """Category dropdown has the seven canonical values in order (DoD)."""
        resp = logged_in_client.get(f"/expenses/{owned_expense['id']}/edit")
        body = resp.get_data(as_text=True)
        assert _category_options(body) == EXPENSE_CATEGORIES

    def test_get_form_action_targets_edit_url(
        self, logged_in_client, owned_expense
    ):
        """Form action points at the edit URL (not a hardcoded path) (DoD)."""
        resp = logged_in_client.get(f"/expenses/{owned_expense['id']}/edit")
        body = resp.get_data(as_text=True)
        assert _form_action(body) == f"/expenses/{owned_expense['id']}/edit"

    def test_get_submit_button_says_save_changes(
        self, logged_in_client, owned_expense
    ):
        """Submit button reads 'Save changes' (DoD).

        The spec's templates section calls this out explicitly: "the
        submit button reads `Save changes`".
        """
        resp = logged_in_client.get(f"/expenses/{owned_expense['id']}/edit")
        body = resp.get_data(as_text=True)
        assert _submit_button_text(body) == "Save changes"

    def test_get_cancel_link_points_to_profile(
        self, logged_in_client, owned_expense
    ):
        """A Cancel link points back to /profile (DoD)."""
        resp = logged_in_client.get(f"/expenses/{owned_expense['id']}/edit")
        body = resp.get_data(as_text=True)
        m = re.search(
            r'<a[^>]*href="([^"]*)"[^>]*>\s*Cancel\s*</a>',
            body, re.IGNORECASE,
        )
        assert m is not None
        assert m.group(1) == "/profile"

    def test_template_extends_base_html(self):
        """templates/edit_expense.html extends base.html (DoD)."""
        template_path = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__), "..", "templates", "edit_expense.html"
            )
        )
        with open(template_path, encoding="utf-8") as f:
            source = f.read()
        assert "{% extends" in source
        assert "base.html" in source


class TestCssHygiene:
    """Static rules from CLAUDE.md and the spec, checked against the file on
    disk so a regression cannot slip in unnoticed."""

    def test_edit_expense_css_has_no_hex_values(self):
        """The expense-form CSS rules in style.css use only ``var(--...)`` — no hex.

        Step 8 promoted the .field-error / .expense-form-actions /
        .expense-form-submit rules into the global ``static/css/style.css``
        so the add and edit pages share one source of truth. This test
        pins the no-hex property for those rules specifically, even if
        the rest of style.css is updated later.
        """
        css_path = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__), "..", "static", "css", "style.css"
            )
        )
        with open(css_path, encoding="utf-8") as f:
            css = f.read()
        start = css.find("/* Expense form (add + edit)")
        assert start != -1, "expense form rules not found in style.css"
        rest = css[start + 1:]
        end = rest.find("\n/* ")
        if end == -1:
            rule_block = rest
        else:
            rule_block = rest[:end]
        match = re.search(r"#[0-9a-fA-F]{3,8}\b", rule_block)
        assert match is None, (
            f"hex literal found in expense-form rules of style.css: {match.group(0)!r}"
        )


# ---------------------------------------------------------------------------
# Section 4 — POST happy path (DoD: update, redirect, user_id guard,
# created_at unchanged, new values visible on /profile).
# ---------------------------------------------------------------------------

class TestPostHappyPath:
    """A valid POST updates the row in place and redirects to /profile."""

    @staticmethod
    def _valid_payload():
        return {
            "amount": "55.55",
            "category": "Transport",
            "date": "2026-05-20",
            "description": "Edited note",
        }

    def test_post_valid_redirects_to_profile(
        self, logged_in_client, owned_expense
    ):
        """A valid POST returns 302 to /profile (DoD)."""
        resp = logged_in_client.post(
            f"/expenses/{owned_expense['id']}/edit",
            data=self._valid_payload(),
        )
        assert resp.status_code == 302
        assert "/profile" in resp.headers.get("Location", "")

    def test_post_valid_updates_row_with_new_values(
        self, app, logged_in_client, owned_expense
    ):
        """A valid POST updates amount/category/date/description in place (DoD)."""
        logged_in_client.post(
            f"/expenses/{owned_expense['id']}/edit",
            data=self._valid_payload(),
        )
        row = _fetch_expense(app, owned_expense["id"])
        assert row is not None
        assert abs(row["amount"] - 55.55) < 0.001
        assert row["category"] == "Transport"
        assert row["date"] == "2026-05-20"
        assert row["description"] == "Edited note"

    def test_post_valid_user_id_guard_prevents_cross_user_mutation(
        self, app, logged_in_client, owned_expense, registered_user
    ):
        """user_id is read from session, never from the form (DoD).

        Spec §Validation rules: "user_id is never accepted from the form
        — it is always read from session['user_id']". The test injects a
        hostile user_id in the form body and asserts the row's user_id is
        still the session's.
        """
        payload = self._valid_payload()
        payload["user_id"] = "99999"  # hostile; must be ignored
        logged_in_client.post(
            f"/expenses/{owned_expense['id']}/edit",
            data=payload,
        )
        row = _fetch_expense(app, owned_expense["id"])
        assert row is not None
        assert row["user_id"] == registered_user["id"]
        # Sanity: no row was ever written for the hostile id.
        assert _count_expenses_for_user(app, 99999) == 0

    def test_post_valid_created_at_unchanged(
        self, app, logged_in_client, owned_expense
    ):
        """The row's created_at is unchanged after an edit (DoD).

        Spec §New helpers: "Does not touch created_at — that column
        records the original insert time and is intentionally immutable."
        """
        original = _fetch_expense(app, owned_expense["id"])
        assert original is not None
        original_created_at = original["created_at"]

        logged_in_client.post(
            f"/expenses/{owned_expense['id']}/edit",
            data=self._valid_payload(),
        )
        after = _fetch_expense(app, owned_expense["id"])
        assert after is not None
        assert after["created_at"] == original_created_at

    def test_post_valid_new_values_visible_on_profile(
        self, logged_in_client, owned_expense
    ):
        """After a successful edit, new values are visible on /profile (DoD).

        Uses a unique description string as a needle so the assertion
        is unambiguous: that string is not present before the edit and
        must appear on /profile immediately after the redirect.
        """
        logged_in_client.post(
            f"/expenses/{owned_expense['id']}/edit",
            data={
                "amount": "77.77",
                "category": "Health",
                "date": "2026-05-21",
                "description": "Unique-edit-needle-ABC",
            },
        )
        profile = logged_in_client.get("/profile")
        assert profile.status_code == 200
        body = profile.get_data(as_text=True)
        assert "Unique-edit-needle-ABC" in body

    def test_post_valid_only_targeted_row_updated(
        self, app, logged_in_client, registered_user, owned_expense
    ):
        """Editing row N updates only row N — other rows untouched (DoD).

        Adds a second expense for the same user, edits only the first,
        and verifies the second is byte-for-byte unchanged.
        """
        other_id = _insert_expense(
            app, registered_user["id"],
            amount=7.0, category="Other", date_str="2026-05-10",
            description="untouched",
        )
        logged_in_client.post(
            f"/expenses/{owned_expense['id']}/edit",
            data=self._valid_payload(),
        )
        other_row = _fetch_expense(app, other_id)
        assert other_row is not None
        assert abs(other_row["amount"] - 7.0) < 0.001
        assert other_row["category"] == "Other"
        assert other_row["date"] == "2026-05-10"
        assert other_row["description"] == "untouched"

    def test_post_twice_with_same_data_is_idempotent(
        self, app, logged_in_client, owned_expense
    ):
        """Posting the same valid payload twice is a no-op on the second call (DoD).

        Captures the row's state after the first POST, POSTs the same
        payload again, and asserts every field is unchanged — including
        created_at, which a buggy implementation that always re-stamps
        the row would silently rewrite.
        """
        payload = self._valid_payload()
        logged_in_client.post(
            f"/expenses/{owned_expense['id']}/edit", data=payload
        )
        after_first = _fetch_expense(app, owned_expense["id"])
        logged_in_client.post(
            f"/expenses/{owned_expense['id']}/edit", data=payload
        )
        after_second = _fetch_expense(app, owned_expense["id"])
        assert after_first["amount"] == after_second["amount"]
        assert after_first["category"] == after_second["category"]
        assert after_first["date"] == after_second["date"]
        assert after_first["description"] == after_second["description"]
        assert after_first["created_at"] == after_second["created_at"]


# ---------------------------------------------------------------------------
# Section 5 — Description NULL coercion (DoD: blank → NULL).
# ---------------------------------------------------------------------------

class TestDescriptionCoercion:
    """Description NULL coercion on edit (mirrors Step 7)."""

    def test_post_empty_description_stored_as_null(
        self, app, logged_in_client, owned_expense
    ):
        """Empty description → NULL (DoD)."""
        logged_in_client.post(
            f"/expenses/{owned_expense['id']}/edit",
            data={
                "amount": "10.00",
                "category": "Food",
                "date": "2026-05-15",
                "description": "",
            },
        )
        row = _fetch_expense(app, owned_expense["id"])
        assert row is not None
        assert row["description"] is None

    def test_post_whitespace_description_stored_as_null(
        self, app, logged_in_client, owned_expense
    ):
        """Whitespace-only description → NULL (DoD).

        Spec §Validation rules: "strip whitespace; treat empty string as
        None so the column is NULL rather than ''".
        """
        logged_in_client.post(
            f"/expenses/{owned_expense['id']}/edit",
            data={
                "amount": "10.00",
                "category": "Food",
                "date": "2026-05-15",
                "description": "   ",
            },
        )
        row = _fetch_expense(app, owned_expense["id"])
        assert row is not None
        assert row["description"] is None


# ---------------------------------------------------------------------------
# Section 6 — Validation errors. Each must re-render and not update.
# ---------------------------------------------------------------------------

class TestValidationErrors:
    """Each validation failure re-renders the form and does not update."""

    @staticmethod
    def _assert_rerendered_no_update(resp, app, expense_id, original):
        """Common assertions for any validation-failure path on edit.

        - Status is 200 (form re-rendered, not redirected).
        - The four form fields are still present.
        - The original values are still in the row.
        """
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert 'name="amount"' in body
        assert 'name="category"' in body
        assert 'name="date"' in body

        row = _fetch_expense(app, expense_id)
        assert row is not None
        assert abs(row["amount"] - original["amount"]) < 0.001
        assert row["category"] == original["category"]
        assert row["date"] == original["date"]
        assert row["description"] == original["description"]

    def test_empty_amount_rerenders_no_update(
        self, app, logged_in_client, owned_expense
    ):
        """Empty amount → re-render, no update (DoD)."""
        resp = logged_in_client.post(
            f"/expenses/{owned_expense['id']}/edit",
            data={
                "amount": "",
                "category": "Food",
                "date": "2026-05-15",
                "description": "",
            },
        )
        self._assert_rerendered_no_update(resp, app, owned_expense["id"], owned_expense)

    def test_non_numeric_amount_rerenders_no_update(
        self, app, logged_in_client, owned_expense
    ):
        """Non-numeric amount → re-render, no update (DoD)."""
        resp = logged_in_client.post(
            f"/expenses/{owned_expense['id']}/edit",
            data={
                "amount": "abc",
                "category": "Food",
                "date": "2026-05-15",
                "description": "",
            },
        )
        self._assert_rerendered_no_update(resp, app, owned_expense["id"], owned_expense)

    def test_zero_amount_rerenders_no_update(
        self, app, logged_in_client, owned_expense
    ):
        """Amount of 0 → re-render, no update (DoD).

        Spec §Validation rules: "must be > 0" — zero is not greater than zero.
        """
        resp = logged_in_client.post(
            f"/expenses/{owned_expense['id']}/edit",
            data={
                "amount": "0",
                "category": "Food",
                "date": "2026-05-15",
                "description": "",
            },
        )
        self._assert_rerendered_no_update(resp, app, owned_expense["id"], owned_expense)

    def test_negative_amount_rerenders_no_update(
        self, app, logged_in_client, owned_expense
    ):
        """Negative amount → re-render, no update (DoD)."""
        resp = logged_in_client.post(
            f"/expenses/{owned_expense['id']}/edit",
            data={
                "amount": "-5.00",
                "category": "Food",
                "date": "2026-05-15",
                "description": "",
            },
        )
        self._assert_rerendered_no_update(resp, app, owned_expense["id"], owned_expense)

    def test_empty_category_rerenders_no_update(
        self, app, logged_in_client, owned_expense
    ):
        """Empty category → re-render, no update (DoD)."""
        resp = logged_in_client.post(
            f"/expenses/{owned_expense['id']}/edit",
            data={
                "amount": "10.00",
                "category": "",
                "date": "2026-05-15",
                "description": "",
            },
        )
        self._assert_rerendered_no_update(resp, app, owned_expense["id"], owned_expense)

    def test_bogus_category_rerenders_no_update(
        self, app, logged_in_client, owned_expense
    ):
        """Category outside the canonical seven → re-render, no update (DoD)."""
        resp = logged_in_client.post(
            f"/expenses/{owned_expense['id']}/edit",
            data={
                "amount": "10.00",
                "category": "Hacking",  # not in EXPENSE_CATEGORIES
                "date": "2026-05-15",
                "description": "",
            },
        )
        self._assert_rerendered_no_update(resp, app, owned_expense["id"], owned_expense)

    def test_empty_date_rerenders_no_update(
        self, app, logged_in_client, owned_expense
    ):
        """Empty date → re-render, no update (DoD)."""
        resp = logged_in_client.post(
            f"/expenses/{owned_expense['id']}/edit",
            data={
                "amount": "10.00",
                "category": "Food",
                "date": "",
                "description": "",
            },
        )
        self._assert_rerendered_no_update(resp, app, owned_expense["id"], owned_expense)

    def test_malformed_date_rerenders_no_update(
        self, app, logged_in_client, owned_expense
    ):
        """Malformed date → re-render, no update (DoD).

        Slashes instead of hyphens is the canonical wrong format.
        """
        resp = logged_in_client.post(
            f"/expenses/{owned_expense['id']}/edit",
            data={
                "amount": "10.00",
                "category": "Food",
                "date": "2026/05/15",
                "description": "",
            },
        )
        self._assert_rerendered_no_update(resp, app, owned_expense["id"], owned_expense)

    def test_future_date_rerenders_no_update(
        self, app, logged_in_client, owned_expense
    ):
        """Future date → re-render, no update (DoD).

        2099-01-01 is unambiguously in the future regardless of how the
        implementation computes "today".
        """
        resp = logged_in_client.post(
            f"/expenses/{owned_expense['id']}/edit",
            data={
                "amount": "10.00",
                "category": "Food",
                "date": "2099-01-01",
                "description": "",
            },
        )
        self._assert_rerendered_no_update(resp, app, owned_expense["id"], owned_expense)


# ---------------------------------------------------------------------------
# Section 7 — Round-trip on error (DoD: previously submitted valid fields
# keep their values when the form is re-rendered, NOT the row's values).
# ---------------------------------------------------------------------------

class TestRoundTripOnError:
    """On a validation error, valid fields keep the user's submitted values."""

    def test_invalid_amount_keeps_other_field_values(
        self, logged_in_client, owned_expense
    ):
        """Invalid amount → category, date, description rehydrate (DoD).

        The original row has category=Food, date=2026-05-15,
        description="Original description". Submitting amount='abc' with
        a *different* category/date/description must rehydrate the form
        with what the user just typed. A buggy implementation that
        re-pulls from the row would show "Food" / "2026-05-15" /
        "Original description" instead.
        """
        resp = logged_in_client.post(
            f"/expenses/{owned_expense['id']}/edit",
            data={
                "amount": "abc",  # invalid — the only bad field
                "category": "Bills",
                "date": "2026-04-15",
                "description": "Round-trip me please",
            },
        )
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)

        # Category: the submitted "Bills" should be the selected option.
        assert _selected_category(body) == "Bills"
        # Date: the date input rehydrates with the submitted value.
        assert _input_value(body, "date") == "2026-04-15"
        # Description: the textarea content contains the submitted text.
        ta = _textarea_content(body, "description")
        assert ta is not None
        assert "Round-trip me please" in ta
        # The invalid amount is also preserved so the user sees what they typed.
        assert _input_value(body, "amount") == "abc"


# ---------------------------------------------------------------------------
# Section 8 — Profile entry point (DoD: each row in the recent-transactions
# table on /profile has a working Edit link to /expenses/<id>/edit).
# ---------------------------------------------------------------------------

class TestProfileEntryPoint:
    """The /profile page exposes a working Edit link per transaction row."""

    def test_profile_has_edit_link_per_row(
        self, app, logged_in_client, registered_user
    ):
        """/profile body contains a link to /expenses/<id>/edit per row (DoD).

        Seeds three expenses for the same user and asserts that each
        appears as a working edit link on the /profile page.
        """
        ids = []
        for i, (amt, cat) in enumerate(
            [(10.0, "Food"), (20.0, "Transport"), (30.0, "Bills")]
        ):
            eid = _insert_expense(
                app, registered_user["id"],
                amount=amt, category=cat, date_str=f"2026-05-{i+1:02d}",
                description=f"row {i}",
            )
            ids.append(eid)

        resp = logged_in_client.get("/profile")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        # Each row id must have a corresponding /expenses/<id>/edit link.
        for eid in ids:
            assert _has_link_to(body, f"/expenses/{eid}/edit"), (
                f"missing Edit link to /expenses/{eid}/edit"
            )

    def test_profile_edit_anchor_never_points_at_hash(
        self, app, logged_in_client, registered_user
    ):
        """No Edit anchor on /profile points at '#' (DoD).

        Walks every <a>...</a> that contains the word "Edit" and asserts
        that none of them uses href="#". Guards against the
        "the table is wired up but the link target is a placeholder"
        regression.
        """
        _insert_expense(
            app, registered_user["id"],
            amount=10.0, category="Food", date_str="2026-05-01",
            description="one",
        )
        resp = logged_in_client.get("/profile")
        body = resp.get_data(as_text=True)
        anchors = re.findall(
            r"<a[^>]*>[^<]*Edit[^<]*</a>", body, re.IGNORECASE
        )
        assert anchors, "no Edit-labelled anchor on /profile"
        for anchor in anchors:
            assert 'href="#"' not in anchor and "href='#'" not in anchor, (
                f"Edit-labelled anchor still points at '#': {anchor!r}"
            )
