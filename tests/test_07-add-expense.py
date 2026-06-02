"""Black-box test suite for Spendly spec 07 — Add expense.

Derived from `.claude/specs/07-add-expense.md` Definition of done. Tests
target the public HTTP interface (`GET` / `POST /expenses/add`) and the
observable DB state via direct ``SELECT`` queries — never via importing
the route handlers or DB helpers under test.

The conftest freezes "today" at 2026-06-01 (FROZEN_TODAY) via the
``frozen_today`` fixture, so "pre-filled with today's date" assertions
are deterministic. The conftest also seeds the DB with a Demo User (8
expenses) and registers a separate Test User (0 expenses); these tests
log in as Test User, so the per-user expense count starts at 0.
"""

import os
import re
import datetime

import database.db as db_module
from database.db import EXPENSE_CATEGORIES


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


def _count_all_expenses(app):
    """Return the total number of rows in the expenses table."""
    with app.app_context():
        with db_module.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM expenses")
            return int(cursor.fetchone()[0])


def _latest_expense_for_user(app, user_id):
    """Return the most recently inserted expense for ``user_id``, or None."""
    with app.app_context():
        with db_module.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM expenses WHERE user_id = ? "
                "ORDER BY id DESC LIMIT 1",
                (user_id,),
            )
            return cursor.fetchone()


def _input_value(html, name):
    """Return the value attribute of ``<input name="<name>" ...>`` or None."""
    pattern = r'<input[^>]*name="' + re.escape(name) + r'"[^>]*value="([^"]*)"'
    m = re.search(pattern, html)
    if m:
        return m.group(1)
    # Allow the reverse attribute order.
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
    """Return the list of non-empty option values inside the category select.

    Filters out a placeholder option (``value=""``) so the test only sees
    the real category values the spec promises.
    """
    inner = _category_select_inner(html)
    values = re.findall(r'<option[^>]*value="([^"]*)"', inner)
    return [v for v in values if v != ""]


def _selected_category(html):
    """Return the value of the selected option inside ``<select name="category">``.

    Skips a placeholder option whose ``selected`` is just used as the default
    state — only a non-empty selected value counts as a chosen category.
    """
    inner = _category_select_inner(html)
    # value before selected
    m = re.search(
        r'<option[^>]*value="([^"]*)"[^>]*\bselected\b[^>]*>', inner
    )
    if m and m.group(1):
        return m.group(1)
    # selected before value
    m = re.search(
        r'<option[^>]*\bselected\b[^>]*value="([^"]*)"[^>]*>', inner
    )
    if m and m.group(1):
        return m.group(1)
    return None


def _cancel_link_href(html):
    """Return the href of the ``<a>Cancel</a>`` link, or None if not present."""
    m = re.search(
        r'<a[^>]*href="([^"]*)"[^>]*>\s*Cancel\s*</a>', html, re.IGNORECASE
    )
    return m.group(1) if m else None


def _has_link_to(html, target):
    """True if any anchor has ``href="<target>"`` (single or double quotes)."""
    return f'href="{target}"' in html or f"href='{target}'" in html


# ---------------------------------------------------------------------------
# Section 1 — Auth guards (DoD: GET unauthenticated, POST unauthenticated).
# ---------------------------------------------------------------------------

class TestAuthGuards:
    """The add-expense route is auth-gated on both GET and POST."""

    def test_get_unauthenticated_redirects_to_login(self, client):
        """GET /expenses/add (not logged in) redirects to /login (DoD)."""
        resp = client.get("/expenses/add")
        assert resp.status_code == 302
        assert "/login" in resp.headers.get("Location", "")

    def test_post_unauthenticated_redirects_to_login(self, client):
        """POST /expenses/add (not logged in) redirects to /login (DoD)."""
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "10.00",
                "category": "Food",
                "date": TODAY.isoformat(),
                "description": "sneaky",
            },
        )
        assert resp.status_code == 302
        assert "/login" in resp.headers.get("Location", "")

    def test_post_unauthenticated_does_not_insert(self, app, client):
        """POST /expenses/add (not logged in) must NOT insert a row (DoD).

        Compares the total expense count before and after the unauthenticated
        POST — the seed_db rows must be untouched and no new row added.
        """
        before = _count_all_expenses(app)
        client.post(
            "/expenses/add",
            data={
                "amount": "10.00",
                "category": "Food",
                "date": TODAY.isoformat(),
                "description": "sneaky",
            },
        )
        assert _count_all_expenses(app) == before


# ---------------------------------------------------------------------------
# Section 2 — GET happy path (DoD: form rendered, today prefill, categories,
# Cancel link, template extends base.html).
# ---------------------------------------------------------------------------

class TestGetForm:
    """Logged-in GET /expenses/add renders the form correctly."""

    def test_get_returns_200_with_form(self, logged_in_client):
        """GET /expenses/add returns 200 with the four form fields (DoD)."""
        resp = logged_in_client.get("/expenses/add")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        # Spec §Form lists exactly these four named fields.
        assert 'name="amount"' in body
        assert 'name="category"' in body
        assert 'name="date"' in body
        assert 'name="description"' in body

    def test_get_date_input_prefilled_with_today(
        self, logged_in_client, frozen_today
    ):
        """The date input is pre-filled with today's date (DoD).

        ``frozen_today`` patches the app's notion of today to 2026-06-01.
        The spec says the date defaults to "today's date" so a correct
        implementation will use the same helper and the value will be
        deterministic in tests.
        """
        resp = logged_in_client.get("/expenses/add")
        body = resp.get_data(as_text=True)
        assert _input_value(body, "date") == TODAY.isoformat()

    def test_get_category_dropdown_contains_canonical_values_in_order(
        self, logged_in_client
    ):
        """Category dropdown has exactly the seven canonical values, in order (DoD).

        Spec §Categories: "Food, Transport, Bills, Health, Entertainment,
        Shopping, Other" — in that order.
        """
        resp = logged_in_client.get("/expenses/add")
        body = resp.get_data(as_text=True)
        options = _category_options(body)
        assert options == EXPENSE_CATEGORIES

    def test_get_cancel_link_points_to_profile(self, logged_in_client):
        """A Cancel link points back to /profile (DoD).

        Spec §Form: "A Cancel link back to url_for('profile')". This
        asserts on the actual anchor text "Cancel" so a generic nav-link
        to /profile would not satisfy the test.
        """
        resp = logged_in_client.get("/expenses/add")
        body = resp.get_data(as_text=True)
        cancel_href = _cancel_link_href(body)
        assert cancel_href is not None, "no <a>Cancel</a> anchor found"
        assert cancel_href == "/profile"

    def test_template_extends_base_html(self):
        """templates/add_expense.html extends base.html (DoD).

        Structural assertion: the spec says "Create: templates/add_expense.html
        — extends base.html". This guards against the template being a
        standalone HTML file.
        """
        template_path = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__), "..", "templates", "add_expense.html"
            )
        )
        with open(template_path, encoding="utf-8") as f:
            source = f.read()
        assert "{% extends" in source
        assert "base.html" in source


class TestCssHygiene:
    """Static rules from CLAUDE.md and the spec, checked against the file on
    disk so a regression cannot slip in unnoticed."""

    def test_expense_form_rules_have_no_hex_values(self):
        """The expense-form CSS rules use only ``var(--...)`` — no hex.

        Step 8 moved the .field-error / .expense-form-actions /
        .expense-form-submit rules into ``static/css/style.css`` (global)
        so the add and edit pages share one source of truth. This test
        pins the no-hex property for those rules specifically — a
        regression that hardcodes a colour into any of them will fail
        this test, even if the rest of style.css is unchanged.
        """
        css_path = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__), "..", "static", "css", "style.css"
            )
        )
        with open(css_path, encoding="utf-8") as f:
            css = f.read()
        # Slice the css down to the three rules Step 8 added. The start
        # anchor is "/* Expense form (add + edit)" and we stop at the
        # next /* … */ comment block boundary, or end of file. This
        # keeps the assertion scoped to the new rules.
        start = css.find("/* Expense form (add + edit)")
        assert start != -1, "expense form rules not found in style.css"
        # Walk forward to the next top-level /* comment opener that is
        # not the start anchor. The first subsequent /* that starts a
        # new top-level comment ends our slice.
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
# Section 3 — POST happy path (DoD: insert, redirect, user_id from session,
# created_at auto-populated, row visible on /profile).
# ---------------------------------------------------------------------------

class TestPostHappyPath:
    """A valid POST inserts the expense and redirects to /profile."""

    @staticmethod
    def _valid_payload():
        return {
            "amount": "12.50",
            "category": "Food",
            "date": "2026-05-30",
            "description": "Coffee and pastry",
        }

    def test_post_valid_redirects_to_profile(self, logged_in_client):
        """A valid POST returns 302 with Location pointing at /profile (DoD)."""
        resp = logged_in_client.post(
            "/expenses/add", data=self._valid_payload()
        )
        assert resp.status_code == 302
        assert "/profile" in resp.headers.get("Location", "")

    def test_post_valid_inserts_row_with_correct_fields(
        self, app, logged_in_client, registered_user
    ):
        """A valid POST inserts exactly one row with the submitted values (DoD)."""
        before = _count_expenses_for_user(app, registered_user["id"])
        logged_in_client.post("/expenses/add", data=self._valid_payload())
        after = _count_expenses_for_user(app, registered_user["id"])
        assert after == before + 1
        row = _latest_expense_for_user(app, registered_user["id"])
        assert row is not None
        # Spec §Validation rules: amount stored as the parsed float.
        assert row["amount"] == 12.50
        assert row["category"] == "Food"
        assert row["date"] == "2026-05-30"
        assert row["description"] == "Coffee and pastry"

    def test_post_valid_user_id_is_session_user_not_form(
        self, app, logged_in_client, registered_user
    ):
        """user_id is always read from session, never accepted from the form (DoD).

        Spec §Validation rules: "user_id is never accepted from the form —
        it is always read from session['user_id']".
        """
        payload = self._valid_payload()
        # Inject a hostile user_id in the form; the route MUST ignore it.
        payload["user_id"] = "99999"
        logged_in_client.post("/expenses/add", data=payload)
        row = _latest_expense_for_user(app, registered_user["id"])
        assert row is not None
        assert row["user_id"] == registered_user["id"]
        # And no row landed on the hostile id.
        assert _count_expenses_for_user(app, 99999) == 0

    def test_post_valid_created_at_auto_populated(
        self, app, logged_in_client, registered_user
    ):
        """The new row's created_at is auto-populated by SQLite (DoD).

        Spec §Database changes: "created_at TEXT default datetime('now')".
        """
        logged_in_client.post("/expenses/add", data=self._valid_payload())
        row = _latest_expense_for_user(app, registered_user["id"])
        assert row is not None
        assert row["created_at"] is not None
        assert str(row["created_at"]).strip() != ""

    def test_post_valid_row_appears_on_profile(self, logged_in_client):
        """After the redirect, the new row is visible on /profile (DoD).

        Uses a unique description string as a "needle" so finding it in the
        rendered profile body unambiguously proves the row is in the
        recent-transactions table.
        """
        logged_in_client.post(
            "/expenses/add",
            data={
                "amount": "33.33",
                "category": "Transport",
                "date": "2026-05-15",
                "description": "Unique-needle-XYZ",
            },
        )
        profile = logged_in_client.get("/profile")
        assert profile.status_code == 200
        assert "Unique-needle-XYZ" in profile.get_data(as_text=True)


# ---------------------------------------------------------------------------
# Section 4 — Description NULL coercion (DoD: blank description -> NULL).
# ---------------------------------------------------------------------------

class TestDescriptionCoercion:
    """The description column is NULL when the user submits empty/blank text."""

    def test_post_empty_description_stored_as_null(
        self, app, logged_in_client, registered_user
    ):
        """An empty description is stored as NULL, not '' (DoD).

        Spec §Validation rules: "treat empty string as None so the column is
        NULL rather than ''".
        """
        logged_in_client.post(
            "/expenses/add",
            data={
                "amount": "5.00",
                "category": "Other",
                "date": "2026-04-01",
                "description": "",
            },
        )
        row = _latest_expense_for_user(app, registered_user["id"])
        assert row is not None
        assert row["description"] is None

    def test_post_whitespace_description_stored_as_null(
        self, app, logged_in_client, registered_user
    ):
        """A whitespace-only description is stripped then stored as NULL.

        Spec §Validation rules: "strip whitespace; treat empty string as
        None".
        """
        logged_in_client.post(
            "/expenses/add",
            data={
                "amount": "5.00",
                "category": "Other",
                "date": "2026-04-01",
                "description": "   ",
            },
        )
        row = _latest_expense_for_user(app, registered_user["id"])
        assert row is not None
        assert row["description"] is None


# ---------------------------------------------------------------------------
# Section 5 — Validation errors (one DoD item per test).
# Each failure must re-render the form (status 200) AND insert nothing.
# ---------------------------------------------------------------------------

class TestValidationErrors:
    """Each validation failure re-renders the form and inserts nothing."""

    @staticmethod
    def _assert_rerendered_no_insert(resp, app, user_id):
        """Common assertions for any validation-failure path.

        - Status is 200 (form re-rendered, not redirected).
        - The four form fields are still present (the form was re-shown).
        - No expense row was inserted for the logged-in user.
        """
        assert resp.status_code == 200, (
            f"validation failure should re-render (200), got {resp.status_code}"
        )
        body = resp.get_data(as_text=True)
        assert 'name="amount"' in body
        assert 'name="category"' in body
        assert 'name="date"' in body
        assert _count_expenses_for_user(app, user_id) == 0

    def test_empty_amount_rerenders_no_insert(
        self, app, logged_in_client, registered_user
    ):
        """Empty amount → form re-rendered, no insert (DoD)."""
        resp = logged_in_client.post(
            "/expenses/add",
            data={
                "amount": "",
                "category": "Food",
                "date": "2026-05-30",
                "description": "",
            },
        )
        self._assert_rerendered_no_insert(resp, app, registered_user["id"])

    def test_non_numeric_amount_rerenders_no_insert(
        self, app, logged_in_client, registered_user
    ):
        """Non-numeric amount ('abc') → form re-rendered, no insert (DoD)."""
        resp = logged_in_client.post(
            "/expenses/add",
            data={
                "amount": "abc",
                "category": "Food",
                "date": "2026-05-30",
                "description": "",
            },
        )
        self._assert_rerendered_no_insert(resp, app, registered_user["id"])

    def test_zero_amount_rerenders_no_insert(
        self, app, logged_in_client, registered_user
    ):
        """Amount of 0 → form re-rendered, no insert (DoD).

        Spec §Validation rules: "must be > 0" — zero is not greater than zero.
        """
        resp = logged_in_client.post(
            "/expenses/add",
            data={
                "amount": "0",
                "category": "Food",
                "date": "2026-05-30",
                "description": "",
            },
        )
        self._assert_rerendered_no_insert(resp, app, registered_user["id"])

    def test_negative_amount_rerenders_no_insert(
        self, app, logged_in_client, registered_user
    ):
        """Negative amount → form re-rendered, no insert (DoD)."""
        resp = logged_in_client.post(
            "/expenses/add",
            data={
                "amount": "-5.00",
                "category": "Food",
                "date": "2026-05-30",
                "description": "",
            },
        )
        self._assert_rerendered_no_insert(resp, app, registered_user["id"])

    def test_empty_category_rerenders_no_insert(
        self, app, logged_in_client, registered_user
    ):
        """Empty category → form re-rendered, no insert (DoD)."""
        resp = logged_in_client.post(
            "/expenses/add",
            data={
                "amount": "10.00",
                "category": "",
                "date": "2026-05-30",
                "description": "",
            },
        )
        self._assert_rerendered_no_insert(resp, app, registered_user["id"])

    def test_bogus_category_rerenders_no_insert(
        self, app, logged_in_client, registered_user
    ):
        """A category outside the canonical seven is rejected (DoD).

        Spec §Validation rules: "must be one of the seven canonical values
        (reject any other string)". The test bypasses the HTML <select>
        constraint by submitting raw form data.
        """
        resp = logged_in_client.post(
            "/expenses/add",
            data={
                "amount": "10.00",
                "category": "Hacking",  # not in EXPENSE_CATEGORIES
                "date": "2026-05-30",
                "description": "",
            },
        )
        self._assert_rerendered_no_insert(resp, app, registered_user["id"])

    def test_empty_date_rerenders_no_insert(
        self, app, logged_in_client, registered_user
    ):
        """Empty date → form re-rendered, no insert (DoD)."""
        resp = logged_in_client.post(
            "/expenses/add",
            data={
                "amount": "10.00",
                "category": "Food",
                "date": "",
                "description": "",
            },
        )
        self._assert_rerendered_no_insert(resp, app, registered_user["id"])

    def test_malformed_date_rerenders_no_insert(
        self, app, logged_in_client, registered_user
    ):
        """Malformed date (wrong separator) → form re-rendered, no insert (DoD).

        Spec §Validation rules: "must parse as YYYY-MM-DD". Slashes are
        the canonical example of a wrong format.
        """
        resp = logged_in_client.post(
            "/expenses/add",
            data={
                "amount": "10.00",
                "category": "Food",
                "date": "2026/05/30",
                "description": "",
            },
        )
        self._assert_rerendered_no_insert(resp, app, registered_user["id"])

    def test_future_date_rerenders_no_insert(
        self, app, logged_in_client, registered_user
    ):
        """A date in the future → form re-rendered, no insert (DoD).

        Spec §Validation rules: "must not be in the future". 2099-01-01 is
        unambiguously in the future regardless of how the implementation
        computes "today".
        """
        resp = logged_in_client.post(
            "/expenses/add",
            data={
                "amount": "10.00",
                "category": "Food",
                "date": "2099-01-01",
                "description": "",
            },
        )
        self._assert_rerendered_no_insert(resp, app, registered_user["id"])


# ---------------------------------------------------------------------------
# Section 6 — Round-trip on error (DoD: previously submitted valid fields
# keep their values when the form is re-rendered).
# ---------------------------------------------------------------------------

class TestRoundTripOnError:
    """On a validation error, valid fields keep their submitted values."""

    def test_invalid_amount_keeps_other_field_values(
        self, app, logged_in_client, registered_user
    ):
        """Invalid amount → category, date, description rehydrate (DoD).

        Spec §Form: "On error, all valid fields keep their submitted values
        (round-trip) so the user does not have to re-type them".
        """
        resp = logged_in_client.post(
            "/expenses/add",
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

        # And nothing was inserted.
        assert _count_expenses_for_user(app, registered_user["id"]) == 0


# ---------------------------------------------------------------------------
# Section 7 — Profile entry point (DoD: /profile has a real link to /expenses/add).
# ---------------------------------------------------------------------------

class TestProfileEntryPoint:
    """The /profile page exposes a real link to /expenses/add."""

    def test_profile_has_link_to_add_expense(self, logged_in_client):
        """/profile body contains a link to /expenses/add, not href="#" (DoD).

        Spec §Templates: "the existing 'Add expense' link/button on the
        profile page should already target url_for('add_expense')". The
        check guards against both a hardcoded path and a placeholder '#'.
        """
        resp = logged_in_client.get("/profile")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        # url_for('add_expense') resolves to /expenses/add given the routing.
        assert _has_link_to(body, "/expenses/add")
        # Anti-regression: no 'Add'-labelled anchor should be href="#".
        anchors = re.findall(
            r"<a[^>]*>[^<]*Add[^<]*</a>", body, re.IGNORECASE
        )
        for anchor in anchors:
            assert 'href="#"' not in anchor and "href='#'" not in anchor, (
                f"Add-labelled anchor still points at placeholder '#': {anchor!r}"
            )
