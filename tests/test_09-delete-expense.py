"""Black-box test suite for Spendly spec 09 — Delete expense.

Derived from `.claude/specs/09-delete-expense.md` Definition of done. Tests
target the public HTTP interface (`GET` / `POST /expenses/<id>/delete`) and
the observable DB state via direct ``SELECT`` queries — never via
importing the route handlers. The new `delete_expense` DB helper is
exercised directly under the `TestDeleteExpenseHelper` class so a future
caller (e.g. a bulk-delete admin tool) can trust the rowcount return
contract.

The conftest freezes "today" at 2026-06-01 (FROZEN_TODAY) via the
``frozen_today`` fixture, so date-based assertions on the profile page
are deterministic regardless of when the tests are executed.

All fixtures are local to this file except those reused from conftest
(`app`, `client`, `logged_in_client`, `registered_user`, `frozen_today`).
If `other_user` / `other_logged_in_client` / `owned_expense` become
useful to other test files in the future, they can be promoted to
conftest.py.
"""

import os
import re
import datetime

import pytest

import database.db as db_module
from werkzeug.security import generate_password_hash


# The conftest's FROZEN_TODAY value. Kept local so each assertion reads
# naturally beside the dates it compares against.
TODAY = datetime.date(2026, 6, 1)


# ---------------------------------------------------------------------------
# Helpers — pure HTML / DB inspection utilities.
# None of them know anything about the route implementation; they only know
# the shapes the spec describes (a single POST form, a Cancel link, a
# destructive button labelled "Delete expense", and the `expenses` table).
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


def _has_button_with_class(html, klass):
    """True if a <button ... class="...klass..."> is present.

    The spec requires the destructive button to use ``btn-danger`` as one
    of its classes; we allow extra classes in the value but insist the
    class attribute contains the exact token.
    """
    pattern = r'<button[^>]*\bclass="([^"]*)"[^>]*>'
    for m in re.finditer(pattern, html):
        classes = m.group(1).split()
        if klass in classes:
            return True
    return False


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
        amount=45.00, category="Food", date_str="2026-05-29",
        description="Lunch with team",
    )
    return {
        "id": expense_id,
        "amount": 45.00,
        "category": "Food",
        "date": "2026-05-29",
        "description": "Lunch with team",
    }


# ---------------------------------------------------------------------------
# Section 1 — Auth guards (DoD: GET/POST unauthenticated → /login, no delete).
# ---------------------------------------------------------------------------

class TestAuthGuards:
    """The delete-expense route is auth-gated on both GET and POST."""

    def test_get_unauthenticated_redirects_to_login(self, client, owned_expense):
        """GET /expenses/<id>/delete (not logged in) → /login (DoD)."""
        resp = client.get(f"/expenses/{owned_expense['id']}/delete")
        assert resp.status_code == 302
        assert "/login" in resp.headers.get("Location", "")

    def test_post_unauthenticated_redirects_to_login(self, client, owned_expense):
        """POST /expenses/<id>/delete (not logged in) → /login (DoD)."""
        resp = client.post(f"/expenses/{owned_expense['id']}/delete")
        assert resp.status_code == 302
        assert "/login" in resp.headers.get("Location", "")

    def test_post_unauthenticated_does_not_delete(self, app, client, owned_expense):
        """POST /expenses/<id>/delete (not logged in) must NOT delete the row (DoD).

        Spec §Redirect / success: "The route is auth-gated: a GET or POST
        without ``session['user_id']`` redirects to ``/login`` and does
        not delete." Asserts by row count: the row is still there with
        its original fields intact.
        """
        before = _count_expenses_for_user(app, _fetch_expense(app, owned_expense["id"])["user_id"])
        client.post(f"/expenses/{owned_expense['id']}/delete")
        row = _fetch_expense(app, owned_expense["id"])
        assert row is not None
        # Amount / category / date / description all unchanged.
        assert abs(row["amount"] - owned_expense["amount"]) < 0.001
        assert row["category"] == owned_expense["category"]
        assert row["date"] == owned_expense["date"]
        assert row["description"] == owned_expense["description"]
        # And the per-user count is unchanged.
        after = _count_expenses_for_user(app, row["user_id"])
        assert after == before


# ---------------------------------------------------------------------------
# Section 2 — 404 for missing rows and other-user rows (DoD).
# ---------------------------------------------------------------------------

class TestOwnershipAnd404:
    """404 for missing rows AND for rows the user does not own (DoD)."""

    def test_get_missing_id_returns_404(self, logged_in_client):
        """GET a non-existent id → 404 (DoD)."""
        resp = logged_in_client.get("/expenses/99999/delete")
        assert resp.status_code == 404

    def test_post_missing_id_returns_404(self, logged_in_client):
        """POST to a non-existent id → 404 (DoD)."""
        resp = logged_in_client.post("/expenses/99999/delete")
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
        resp = other_logged_in_client.get(f"/expenses/{eid}/delete")
        assert resp.status_code == 404

    def test_post_other_users_row_returns_404_and_does_not_delete(
        self, app, other_logged_in_client, registered_user
    ):
        """POST to a row owned by another user → 404 AND row unchanged (DoD).

        The spec §Ownership and 404 handling is explicit: "The id exists
        but its ``user_id`` does not match ``session['user_id']`` → 404
        (not 403, to avoid confirming the row's existence)". The
        follow-on invariant is that the row must still be there.
        """
        eid = _insert_expense(
            app, registered_user["id"],
            amount=10.0, category="Food", date_str="2026-05-01",
            description="not yours",
        )
        resp = other_logged_in_client.post(f"/expenses/{eid}/delete")
        assert resp.status_code == 404
        # And the row must still exist byte-for-byte unchanged.
        row = _fetch_expense(app, eid)
        assert row is not None
        assert abs(row["amount"] - 10.0) < 0.001
        assert row["category"] == "Food"
        assert row["description"] == "not yours"
        assert row["date"] == "2026-05-01"


# ---------------------------------------------------------------------------
# Section 3 — Confirmation page rendering (DoD: date, category, amount,
# description rendered; Cancel link; destructive button class; extends
# base.html; form action points at delete URL).
# ---------------------------------------------------------------------------

class TestConfirmationPage:
    """Logged-in GET /expenses/<id>/delete renders the confirmation page."""

    def test_get_returns_200(self, logged_in_client, owned_expense):
        """GET returns 200 for a row the user owns (DoD)."""
        resp = logged_in_client.get(f"/expenses/{owned_expense['id']}/delete")
        assert resp.status_code == 200

    def test_confirmation_page_shows_row_date(
        self, logged_in_client, owned_expense
    ):
        """Confirmation page shows the row's date as stored (DoD).

        Spec §Definition of done: "The confirmation page shows the
        row's ``date`` exactly as stored (e.g. ``2026-05-29``)". The
        fixture row uses 2026-05-29 verbatim.
        """
        resp = logged_in_client.get(f"/expenses/{owned_expense['id']}/delete")
        body = resp.get_data(as_text=True)
        assert "2026-05-29" in body

    def test_confirmation_page_shows_row_category(
        self, logged_in_client, owned_expense
    ):
        """Confirmation page shows the row's category (DoD)."""
        resp = logged_in_client.get(f"/expenses/{owned_expense['id']}/delete")
        body = resp.get_data(as_text=True)
        assert "Food" in body

    def test_confirmation_page_shows_amount_via_format_inr(
        self, logged_in_client, owned_expense
    ):
        """Confirmation page shows the amount formatted as ``₹<amount>`` (DoD).

        Spec §Confirmation page (UI): "``Amount`` (formatted as
        ``₹<amount>`` via ``format_inr``)". The fixture inserts 45.00;
        the spec's example DoD bullet uses ``₹45`` for the same input.
        The ``format_inr`` helper uses ``int(round(amount))`` so
        ``45.00`` → ``₹45``.
        """
        resp = logged_in_client.get(f"/expenses/{owned_expense['id']}/delete")
        body = resp.get_data(as_text=True)
        assert "₹45" in body

    @pytest.mark.parametrize("amount, expected_glyph", [
        (45.00, "₹45"),
        (100.00, "₹100"),
        (1234.40, "₹1,234"),
    ])
    def test_confirmation_page_amount_uses_format_inr_for_various_amounts(
        self, app, logged_in_client, registered_user, amount, expected_glyph
    ):
        """The amount rendering passes through ``format_inr`` (DoD).

        Three independent amounts with three independent expected
        ``₹...`` strings — any hard-coded constant that accidentally
        passes one case will fail the others.
        """
        eid = _insert_expense(
            app, registered_user["id"],
            amount=amount, category="Food", date_str="2026-05-29",
            description="x",
        )
        resp = logged_in_client.get(f"/expenses/{eid}/delete")
        body = resp.get_data(as_text=True)
        assert expected_glyph in body

    def test_confirmation_page_shows_description(
        self, logged_in_client, owned_expense
    ):
        """Confirmation page shows the row's description (DoD)."""
        resp = logged_in_client.get(f"/expenses/{owned_expense['id']}/delete")
        body = resp.get_data(as_text=True)
        assert "Lunch with team" in body

    def test_confirmation_page_shows_dash_for_null_description(
        self, app, logged_in_client, registered_user
    ):
        """Confirmation page shows ``—`` when description is NULL (DoD).

        Spec §Confirmation page (UI): "``Description`` (or ``—`` when
        ``NULL``)". Inserts a fresh row with description=None and
        asserts the em-dash renders in place of the description.
        """
        eid = _insert_expense(
            app, registered_user["id"],
            amount=20.0, category="Other", date_str="2026-04-01",
            description=None,
        )
        resp = logged_in_client.get(f"/expenses/{eid}/delete")
        body = resp.get_data(as_text=True)
        # The em-dash must appear in the rendered page.
        assert "—" in body
        # The literal "None" must not appear (the template should never
        # serialise Python's None to the user).
        assert "None" not in body

    def test_get_form_action_targets_delete_url(
        self, logged_in_client, owned_expense
    ):
        """Form action points at the delete URL (DoD).

        Spec §Confirmation page (UI): "A ``<form method="POST"
        action="{{ url_for('delete_expense', id=expense.id) }}">``
        containing only the submit button."
        """
        resp = logged_in_client.get(f"/expenses/{owned_expense['id']}/delete")
        body = resp.get_data(as_text=True)
        assert _form_action(body) == f"/expenses/{owned_expense['id']}/delete"

    def test_get_submit_button_says_delete_expense(
        self, logged_in_client, owned_expense
    ):
        """Submit button reads 'Delete expense' (DoD)."""
        resp = logged_in_client.get(f"/expenses/{owned_expense['id']}/delete")
        body = resp.get_data(as_text=True)
        assert _submit_button_text(body) == "Delete expense"

    def test_dangerous_button_uses_btn_danger_class(
        self, logged_in_client, owned_expense
    ):
        """The destructive button uses a ``btn-danger`` class (DoD).

        Spec §Rules for implementation: "The destructive button uses a
        ``btn-danger`` class (CSS-variable colour, not a hardcoded hex)
        so it is visually distinct from the primary submit on the
        add/edit forms".
        """
        resp = logged_in_client.get(f"/expenses/{owned_expense['id']}/delete")
        body = resp.get_data(as_text=True)
        assert _has_button_with_class(body, "btn-danger"), (
            "expected a <button> with class 'btn-danger' on the "
            "confirmation page"
        )

    def test_cancel_link_returns_to_profile(
        self, logged_in_client, owned_expense
    ):
        """Cancel link points back to /profile (DoD).

        Spec §Confirmation page (UI): "A ``Cancel`` link back to
        ``url_for('profile')`` that does not submit the form." The
        regex below looks for a plain ``<a>Cancel</a>`` anchor pointing
        at /profile — not a button, which is explicitly forbidden by
        spec §Rules for implementation.
        """
        resp = logged_in_client.get(f"/expenses/{owned_expense['id']}/delete")
        body = resp.get_data(as_text=True)
        m = re.search(
            r'<a[^>]*href="([^"]*)"[^>]*>\s*Cancel\s*</a>',
            body, re.IGNORECASE,
        )
        assert m is not None, "expected a plain <a>Cancel</a> anchor"
        assert m.group(1) == "/profile"

    def test_cancel_link_is_anchor_not_button(
        self, logged_in_client, owned_expense
    ):
        """The Cancel link is an ``<a>``, not a ``<button type="button">`` (DoD).

        Spec §Rules for implementation: "The Cancel link must be a
        plain ``<a href="...">`` (not a ``<button type="button">``)
        so it works without JavaScript".
        """
        resp = logged_in_client.get(f"/expenses/{owned_expense['id']}/delete")
        body = resp.get_data(as_text=True)
        # Look for any <button>Cancel</button> pattern — must not exist.
        assert not re.search(
            r'<button[^>]*>\s*Cancel\s*</button>', body, re.IGNORECASE
        ), "Cancel must be a plain <a>, not a <button>"

    def test_template_extends_base_html(self):
        """templates/delete_expense.html extends base.html (DoD)."""
        template_path = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__), "..", "templates", "delete_expense.html"
            )
        )
        with open(template_path, encoding="utf-8") as f:
            source = f.read()
        assert "{% extends" in source
        assert "base.html" in source

    def test_delete_expense_css_exists_and_uses_no_hex_values(self):
        """static/css/delete-expense.css exists and uses only CSS variables (DoD).

        Spec §Files to create: "the new file is small and only adds
        delete-specific tweaks ... Follows the same CSS-variable
        convention. No hex values." Hex regression guard: a single
        hardcoded color in the new file fails this test.
        """
        css_path = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__), "..", "static", "css", "delete-expense.css"
            )
        )
        assert os.path.exists(css_path), (
            "static/css/delete-expense.css must exist (DoD)"
        )
        with open(css_path, encoding="utf-8") as f:
            css = f.read()
        match = re.search(r"#[0-9a-fA-F]{3,8}\b", css)
        assert match is None, (
            f"hex literal found in delete-expense.css: {match.group(0)!r}"
        )


# ---------------------------------------------------------------------------
# Section 4 — POST commit / redirect / cascade (DoD: delete, commit,
# redirect to /profile, recent-transactions table updated, totals/count/
# breakdown updated).
# ---------------------------------------------------------------------------

class TestDeleteCommit:
    """A valid POST deletes the row, commits, and redirects to /profile."""

    def test_post_valid_redirects_to_profile(
        self, logged_in_client, owned_expense
    ):
        """A valid POST returns 302 to /profile (DoD)."""
        resp = logged_in_client.post(f"/expenses/{owned_expense['id']}/delete")
        assert resp.status_code == 302
        assert "/profile" in resp.headers.get("Location", "")

    def test_post_valid_deletes_row(
        self, app, logged_in_client, owned_expense
    ):
        """A valid POST removes the row from the expenses table (DoD)."""
        logged_in_client.post(f"/expenses/{owned_expense['id']}/delete")
        row = _fetch_expense(app, owned_expense["id"])
        assert row is None, "expected the row to be gone after a successful delete"

    def test_post_valid_deletes_only_targeted_row(
        self, app, logged_in_client, registered_user, owned_expense
    ):
        """Deleting row N removes only row N (DoD).

        Inserts a second expense for the same user, deletes only the
        first, and verifies the second is byte-for-byte unchanged.
        """
        other_id = _insert_expense(
            app, registered_user["id"],
            amount=7.0, category="Other", date_str="2026-05-10",
            description="untouched",
        )
        logged_in_client.post(f"/expenses/{owned_expense['id']}/delete")
        # First row is gone.
        assert _fetch_expense(app, owned_expense["id"]) is None
        # Second row is intact.
        other_row = _fetch_expense(app, other_id)
        assert other_row is not None
        assert abs(other_row["amount"] - 7.0) < 0.001
        assert other_row["category"] == "Other"
        assert other_row["date"] == "2026-05-10"
        assert other_row["description"] == "untouched"

    def test_post_valid_deleted_row_disappears_from_profile(
        self, app, logged_in_client, registered_user, owned_expense
    ):
        """The deleted row is no longer in the recent-transactions table on /profile (DoD).

        Spec §Definition of done: "After a successful delete, the row
        no longer appears in the recent-transactions table on
        ``/profile`` without a manual refresh". Asserts by description
        needle so the assertion is unambiguous.
        """
        # Use a unique description so the test can find/avoid it.
        eid = _insert_expense(
            app, registered_user["id"],
            amount=10.0, category="Food", date_str="2026-05-20",
            description="Unique-delete-needle-XYZ",
        )
        before = logged_in_client.get("/profile")
        assert before.status_code == 200
        assert "Unique-delete-needle-XYZ" in before.get_data(as_text=True)

        logged_in_client.post(f"/expenses/{eid}/delete")

        after = logged_in_client.get("/profile")
        assert after.status_code == 200
        assert "Unique-delete-needle-XYZ" not in after.get_data(as_text=True)

    def test_post_valid_total_spent_updated(
        self, app, logged_in_client, registered_user, owned_expense
    ):
        """After a delete, the profile's total spent reflects the deletion (DoD).

        Spec §Definition of done: "After a successful delete, the
        user's total spent, transaction count, top category, and
        category breakdown on ``/profile`` are all updated to reflect
        the deletion". This test focuses on the total: it inserts two
        rows that sum to a known value, deletes one, and asserts the
        total drops by exactly the deleted row's amount.
        """
        keep_id = _insert_expense(
            app, registered_user["id"],
            amount=10.0, category="Food", date_str="2026-05-15",
            description="keep me",
        )
        before = logged_in_client.get("/profile")
        body_before = before.get_data(as_text=True)
        # Before: total is 10.00 (keep) + 45.00 (fixture) = 55.00 → "₹55".
        assert "₹55" in body_before, (
            f"expected total ₹55 before delete, body: {body_before!r}"
        )

        logged_in_client.post(f"/expenses/{owned_expense['id']}/delete")

        after = logged_in_client.get("/profile")
        body_after = after.get_data(as_text=True)
        # After: total is 10.00 (keep) → "₹10". The fixture row (45) is gone.
        assert "₹10" in body_after, (
            f"expected total ₹10 after delete, body: {body_after!r}"
        )
        # Sanity: keep_id is still there.
        assert _fetch_expense(app, keep_id) is not None

    def test_post_valid_transaction_count_decremented(
        self, app, logged_in_client, registered_user
    ):
        """After a delete, the transaction count on /profile drops by one (DoD).

        Inserts two rows, deletes one, and asserts the count badge on
        /profile drops from 2 to 1. The assertion uses a needle-style
        check: the profile renders the count as a literal integer
        inside the page, so the test pins "2" present and "1" present
        after the delete (without trying to match the surrounding
        markup).
        """
        # Drop the conftest's seed_db rows so the count is exactly 3.
        with app.app_context():
            with db_module.get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM expenses WHERE user_id = ?",
                               (registered_user["id"],))
                conn.commit()
        _insert_expense(
            app, registered_user["id"],
            amount=10.0, category="Food", date_str="2026-05-10",
            description="a",
        )
        eid_b = _insert_expense(
            app, registered_user["id"],
            amount=20.0, category="Food", date_str="2026-05-11",
            description="b",
        )
        del_id = _insert_expense(
            app, registered_user["id"],
            amount=30.0, category="Food", date_str="2026-05-12",
            description="delete me",
        )
        # The transaction count is 3 → "3" appears in the page.
        before = logged_in_client.get("/profile").get_data(as_text=True)
        assert "3" in before
        logged_in_client.post(f"/expenses/{del_id}/delete")
        after = logged_in_client.get("/profile").get_data(as_text=True)
        # Count is now 2.
        assert "2" in after
        # The deleted row's description must not appear on /profile.
        assert "delete me" not in after

    def test_post_valid_category_breakdown_updated(
        self, app, logged_in_client, registered_user
    ):
        """After a delete, the category breakdown on /profile is updated (DoD).

        Sets up two Food rows and one Other row, then deletes the
        single Other row. After the delete, the category breakdown
        must contain "Food" but must not contain "Other".
        """
        # Wipe conftest seed data for this user so the breakdown is
        # driven by these three rows alone.
        with app.app_context():
            with db_module.get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM expenses WHERE user_id = ?",
                               (registered_user["id"],))
                conn.commit()
        food_id = _insert_expense(
            app, registered_user["id"],
            amount=10.0, category="Food", date_str="2026-05-10",
            description="food 1",
        )
        _insert_expense(
            app, registered_user["id"],
            amount=20.0, category="Food", date_str="2026-05-11",
            description="food 2",
        )
        other_id = _insert_expense(
            app, registered_user["id"],
            amount=99.0, category="Bills", date_str="2026-05-12",
            description="bills to delete",
        )

        before = logged_in_client.get("/profile").get_data(as_text=True)
        assert "Bills" in before
        assert "Food" in before

        logged_in_client.post(f"/expenses/{other_id}/delete")

        after = logged_in_client.get("/profile").get_data(as_text=True)
        # "Food" must still be in the breakdown.
        assert "Food" in after
        # "Bills" must be gone (we just removed the only Bills row).
        assert "Bills" not in after

    def test_second_post_after_successful_delete_returns_404(
        self, app, logged_in_client, owned_expense
    ):
        """A second POST after a successful delete returns 404 (DoD).

        Spec §CSRF and idempotency: "The route is NOT idempotent in the
        strict sense — a second POST after a successful delete will
        404 (the row is gone). This is the desired behaviour".
        """
        first = logged_in_client.post(f"/expenses/{owned_expense['id']}/delete")
        assert first.status_code == 302
        second = logged_in_client.post(f"/expenses/{owned_expense['id']}/delete")
        assert second.status_code == 404
        # And the row stays gone.
        assert _fetch_expense(app, owned_expense["id"]) is None

    def test_post_valid_user_id_guard_prevents_cross_user_delete(
        self, app, other_logged_in_client, registered_user
    ):
        """The DELETE is guarded by user_id, so foreign rows survive (DoD).

        Spec §Definition of done: "The ``DELETE`` statement's ``WHERE``
        clause includes ``user_id = ?`` — a user can never delete
        another user's row even if they POST to the right id". The
        route already 404s, but the helper itself enforces the guard
        — this is the integration check.
        """
        eid = _insert_expense(
            app, registered_user["id"],
            amount=50.0, category="Food", date_str="2026-05-01",
            description="owned by registered user",
        )
        # other_user POSTs to the right id.
        resp = other_logged_in_client.post(f"/expenses/{eid}/delete")
        assert resp.status_code == 404
        # The row is still there.
        row = _fetch_expense(app, eid)
        assert row is not None
        assert row["user_id"] == registered_user["id"]


# ---------------------------------------------------------------------------
# Section 5 — Profile entry point (DoD: each row in the recent-transactions
# table on /profile has a working Delete link to /expenses/<id>/delete).
# ---------------------------------------------------------------------------

class TestProfileDeleteLink:
    """The /profile page exposes a working Delete link per transaction row."""

    def test_profile_has_delete_link_per_row(
        self, app, logged_in_client, registered_user
    ):
        """/profile body contains a link to /expenses/<id>/delete per row (DoD).

        Seeds three expenses for the same user and asserts that each
        appears as a working delete link on the /profile page.
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
        for eid in ids:
            assert _has_link_to(body, f"/expenses/{eid}/delete"), (
                f"missing Delete link to /expenses/{eid}/delete"
            )

    def test_profile_delete_link_sits_next_to_edit_link(
        self, app, logged_in_client, registered_user
    ):
        """The Delete link sits next to the existing Edit link in the actions cell (DoD).

        Spec §Files to change: "add a ``Delete`` link ... next to the
        ``Edit`` link Step 8 already wired up". Walks the rendered
        page and asserts that for every row, the row's actions cell
        contains both /expenses/<id>/edit and /expenses/<id>/delete
        anchors.
        """
        eid = _insert_expense(
            app, registered_user["id"],
            amount=10.0, category="Food", date_str="2026-05-01",
            description="one",
        )
        body = logged_in_client.get("/profile").get_data(as_text=True)
        assert _has_link_to(body, f"/expenses/{eid}/edit")
        assert _has_link_to(body, f"/expenses/{eid}/delete")

    def test_profile_delete_anchor_never_points_at_hash(
        self, app, logged_in_client, registered_user
    ):
        """No Delete anchor on /profile points at '#' (DoD).

        Walks every <a>...</a> that contains the word "Delete" and
        asserts that none of them uses href="#". Guards against the
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
            r"<a[^>]*>[^<]*Delete[^<]*</a>", body, re.IGNORECASE
        )
        assert anchors, "no Delete-labelled anchor on /profile"
        for anchor in anchors:
            assert 'href="#"' not in anchor and "href='#'" not in anchor, (
                f"Delete-labelled anchor still points at '#': {anchor!r}"
            )


# ---------------------------------------------------------------------------
# Section 6 — DB helper unit tests (DoD: the new delete_expense helper is
# added to database/db.py and returns the affected rowcount, with the
# user_id guard).
# ---------------------------------------------------------------------------

class TestDeleteExpenseHelper:
    """Direct unit tests on ``database.db.delete_expense``."""

    def test_helper_returns_one_when_row_owned(self, app, isolated_db):
        """Deleting an owned row returns rowcount == 1 and removes the row (DoD).

        The helper's contract: "run ``DELETE FROM expenses WHERE id = ?
        AND user_id = ?``, commit, and return the number of affected
        rows". A successful delete is rowcount == 1 and the row is
        gone from the table.
        """
        from database.db import delete_expense  # local import is fine
        # Seed one row for the isolated user.
        with app.app_context():
            with db_module.get_db() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO expenses (user_id, amount, category, date, description) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (isolated_db["user_id"], 10.0, "Food", "2026-05-01", "x"),
                )
                conn.commit()
                eid = cursor.lastrowid

        rc = delete_expense(isolated_db["user_id"], eid)
        assert rc == 1

        # And the row is gone.
        with app.app_context():
            with db_module.get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM expenses WHERE id = ?", (eid,))
                assert cursor.fetchone() is None

    def test_helper_returns_zero_for_foreign_user_id(self, app, isolated_db):
        """Calling the helper with a foreign user_id returns rowcount == 0 (DoD).

        Spec §New helper: "The ``user_id`` guard ensures a user can
        never delete another user's row". When called with the wrong
        user_id, the WHERE clause excludes the row → 0 affected.
        """
        from database.db import delete_expense
        with app.app_context():
            with db_module.get_db() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO expenses (user_id, amount, category, date, description) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (isolated_db["user_id"], 10.0, "Food", "2026-05-01", "x"),
                )
                conn.commit()
                eid = cursor.lastrowid

        # Foreign user_id (e.g. 99999) — must not delete.
        rc = delete_expense(99999, eid)
        assert rc == 0

        # The row is still there.
        with app.app_context():
            with db_module.get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM expenses WHERE id = ?", (eid,))
                assert cursor.fetchone() is not None

    def test_helper_returns_zero_for_missing_id(self, app, isolated_db):
        """Calling the helper with a non-existent id returns rowcount == 0 (DoD).

        Spec §New helper: "a missing/foreign row will return 0 and the
        route can 404 if it ever does, but the pre-flight
        ``get_expense_by_id`` makes that path unreachable in practice".
        """
        from database.db import delete_expense
        rc = delete_expense(isolated_db["user_id"], 99999)
        assert rc == 0

    def test_helper_uses_parameterised_sql(self, app, isolated_db):
        """The helper uses ``?`` placeholders — no f-string SQL (DoD).

        Spec §Definition of done: "All SQL uses ``?`` placeholders (no
        f-strings, no string concatenation)". The behavioural check:
        an injection-style user_id of "0 OR 1=1" must not affect any
        rows. If the helper ever string-formats the WHERE clause, this
        test will fail by deleting all rows.
        """
        from database.db import delete_expense
        # Seed two rows.
        with app.app_context():
            with db_module.get_db() as conn:
                cursor = conn.cursor()
                for _ in range(2):
                    cursor.execute(
                        "INSERT INTO expenses (user_id, amount, category, date, description) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (isolated_db["user_id"], 10.0, "Food",
                         "2026-05-01", "x"),
                    )
                conn.commit()

        rc = delete_expense("0 OR 1=1", 1)  # hostile user_id string
        assert rc == 0

        # Both rows are still there.
        with app.app_context():
            with db_module.get_db() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM expenses WHERE user_id = ?",
                    (isolated_db["user_id"],),
                )
                assert int(cursor.fetchone()[0]) == 2
