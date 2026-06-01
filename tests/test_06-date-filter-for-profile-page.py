"""Black-box test suite for Spendly spec 06 — Date filter for the profile page.

These tests are derived from `.claude/specs/06-date-filter-for-profile-page.md`
and intentionally do NOT depend on the internal implementation of the filter
resolution or DB helpers. They assert against the public HTTP interface and
the documented behaviour of `database/db.py` helpers.

Today is frozen at 2026-06-01 via the `frozen_today` fixture so the preset
windows are deterministic.
"""

import datetime
import re

import database.db as db_module


# ---------------------------------------------------------------------------
# Helpers used by multiple tests.
# ---------------------------------------------------------------------------

def _user_info_block(html):
    """Return the user-info card HTML so byte-equality can be asserted."""
    m = re.search(r'<div class="profile-card user-info-card">.*?</div>\s*</div>', html, re.DOTALL)
    return m.group(0) if m else ""


def _selected_option_value(html):
    """Return the value of the currently selected <option> in the filter bar."""
    matches = re.findall(r'<option value="([^"]*)"[^>]*\bselected\b', html)
    return matches[0] if matches else None


def _date_input_value(html, name):
    """Return the value attribute of the <input name="from"|"to"> date field."""
    pattern = (
        r'<input[^>]*name="' + re.escape(name) + r'"[^>]*value="([^"]*)"'
    )
    m = re.search(pattern, html)
    if m:
        return m.group(1)
    # The order of attributes may differ — try a more permissive match.
    m2 = re.search(
        r'<input[^>]*value="([^"]*)"[^>]*name="' + re.escape(name) + r'"',
        html,
    )
    return m2.group(1) if m2 else ""


def _stat_value(html, label):
    """Return the rendered value for a stat card whose label is `label`."""
    pattern = (
        r'<span class="stat-label">' + re.escape(label) + r'</span>\s*'
        r'<span class="stat-value">([^<]*)</span>'
    )
    m = re.search(pattern, html)
    return m.group(1).strip() if m else None


def _banner_text(html):
    """Return the contents of the filter-banner <p> or None if not present."""
    m = re.search(r'<p class="filter-banner">\s*(.*?)\s*</p>', html, re.DOTALL)
    return m.group(1).strip() if m else None


def _reset_href(html):
    """Return the href of the Reset link in the filter bar.

    The template renders attributes in the order ``href`` then ``class`` so
    we match that order directly.
    """
    m = re.search(
        r'<a[^>]*href="([^"]*)"[^>]*class="[^"]*filter-reset[^"]*"', html
    )
    if m:
        return m.group(1)
    # Fallback for the opposite attribute order.
    m = re.search(
        r'<a[^>]*class="[^"]*filter-reset[^"]*"[^>]*href="([^"]*)"', html
    )
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Section 1 — Happy paths (Definition of done items 1-6).
# ---------------------------------------------------------------------------

class TestHappyPaths:
    """Spec Definition of done items 1-6."""

    def test_no_query_string_shows_lifetime(self, logged_in_client, known_expenses):
        """Visiting /profile (no query string) still shows lifetime totals (DoD #1)."""
        resp = logged_in_client.get("/profile")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        # No filter active → the Lifetime option is the one selected.
        assert _selected_option_value(html) == ""
        # And the banner is absent.
        assert _banner_text(html) is None

    def test_this_month_filters_to_current_month(self, logged_in_client, known_expenses):
        """?range=this_month shows only the current month (DoD #2)."""
        resp = logged_in_client.get("/profile", query_string={"range": "this_month"})
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert _selected_option_value(html) == "this_month"
        # Exactly one expense lives in the current month in our fixture (offset=0).
        assert _stat_value(html, "Transactions") == "1"
        # Banner present and shows today's date as the upper bound.
        banner = _banner_text(html)
        assert banner is not None
        assert datetime.date(2026, 6, 1).isoformat() in banner
        assert "transactions" in banner

    def test_last_month_excludes_first_of_this_month(self, logged_in_client, known_expenses):
        """?range=last_month excludes the first of the current month (DoD #3)."""
        resp = logged_in_client.get("/profile", query_string={"range": "last_month"})
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert _selected_option_value(html) == "last_month"
        # Banner should show May 2026 as the range, not include June at all.
        banner = _banner_text(html)
        assert banner is not None
        assert "2026-05-01" in banner
        assert "2026-05-31" in banner
        # The first of the current month must NOT appear in the banner or table.
        assert "2026-06-01" not in banner
        # Transaction count for May is 1 (offset=1 in our fixture).
        assert _stat_value(html, "Transactions") == "1"

    def test_last_3_months_wider_window(self, logged_in_client, known_expenses):
        """?range=last_3_months covers this + previous 2 months (DoD #4)."""
        resp = logged_in_client.get("/profile", query_string={"range": "last_3_months"})
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert _selected_option_value(html) == "last_3_months"
        # Three months covered (June, May, April 2026) → 3 expenses.
        assert _stat_value(html, "Transactions") == "3"
        banner = _banner_text(html)
        assert banner is not None
        assert "2026-04-01" in banner
        assert "2026-06-01" in banner

    def test_last_6_months_wider_window(self, logged_in_client, known_expenses):
        """?range=last_6_months covers this + previous 5 months (DoD #4)."""
        resp = logged_in_client.get("/profile", query_string={"range": "last_6_months"})
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert _selected_option_value(html) == "last_6_months"
        # 6 months covered → 6 expenses.
        assert _stat_value(html, "Transactions") == "6"
        banner = _banner_text(html)
        assert banner is not None
        assert "2026-01-01" in banner
        assert "2026-06-01" in banner

    def test_custom_range_with_valid_dates(self, logged_in_client, known_expenses):
        """?range=custom&from=&to= filters to that inclusive range (DoD #5)."""
        resp = logged_in_client.get(
            "/profile",
            query_string={"range": "custom", "from": "2026-02-01", "to": "2026-02-28"},
        )
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert _selected_option_value(html) == "custom"
        # One expense lives in February 2026 (offset=4 in our fixture).
        assert _stat_value(html, "Transactions") == "1"
        # The custom date inputs rehydrate.
        assert _date_input_value(html, "from") == "2026-02-01"
        assert _date_input_value(html, "to") == "2026-02-28"

    def test_from_and_to_without_range_param_is_custom(self, logged_in_client, known_expenses):
        """?from=&to= (no range) is treated identically to range=custom (DoD #6)."""
        resp = logged_in_client.get(
            "/profile",
            query_string={"from": "2026-03-01", "to": "2026-03-31"},
        )
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        # The Custom option should be selected because the URL is a custom range.
        assert _selected_option_value(html) == "custom"
        # One expense lives in March 2026 (offset=3 in our fixture).
        assert _stat_value(html, "Transactions") == "1"


# ---------------------------------------------------------------------------
# Section 2 — Edge cases / fallbacks (Definition of done items 7-10).
# ---------------------------------------------------------------------------

class TestFallbacks:
    """Spec Definition of done items 7-10 — invalid input must fall back to lifetime."""

    def test_malformed_from_date_falls_back_to_lifetime(self, logged_in_client, known_expenses):
        """?from=garbage falls back to lifetime, no 500/400 (DoD #7)."""
        resp = logged_in_client.get(
            "/profile",
            query_string={"from": "garbage", "to": "2026-01-31"},
        )
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        # No filter active → Lifetime selected, banner absent.
        assert _selected_option_value(html) == ""
        assert _banner_text(html) is None
        # Lifetime total = 12 expenses (our fixture).
        assert _stat_value(html, "Transactions") == "12"

    def test_from_greater_than_to_falls_back_to_lifetime(self, logged_in_client, known_expenses):
        """?from=2025-12-31&to=2025-01-01 (from > to) falls back to lifetime (DoD #8)."""
        resp = logged_in_client.get(
            "/profile",
            query_string={"from": "2025-12-31", "to": "2025-01-01"},
        )
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert _selected_option_value(html) == ""
        assert _banner_text(html) is None
        assert _stat_value(html, "Transactions") == "12"

    def test_unknown_preset_falls_back_to_lifetime(self, logged_in_client, known_expenses):
        """?range=banana (unknown preset) falls back to lifetime (DoD #9)."""
        resp = logged_in_client.get(
            "/profile", query_string={"range": "banana"}
        )
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert _selected_option_value(html) == ""
        assert _banner_text(html) is None
        assert _stat_value(html, "Transactions") == "12"

    def test_missing_to_falls_back_to_lifetime(self, logged_in_client, known_expenses):
        """Only `from`, no `to` → falls back to lifetime (DoD #10)."""
        resp = logged_in_client.get(
            "/profile", query_string={"from": "2026-01-01"}
        )
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert _selected_option_value(html) == ""
        assert _banner_text(html) is None
        assert _stat_value(html, "Transactions") == "12"

    def test_missing_from_falls_back_to_lifetime(self, logged_in_client, known_expenses):
        """Only `to`, no `from` → falls back to lifetime (DoD #10)."""
        resp = logged_in_client.get(
            "/profile", query_string={"to": "2026-01-31"}
        )
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert _selected_option_value(html) == ""
        assert _banner_text(html) is None
        assert _stat_value(html, "Transactions") == "12"


# ---------------------------------------------------------------------------
# Section 3 — Auth and invariants.
# ---------------------------------------------------------------------------

class TestAuthAndInvariants:
    """Spec Definition of done items: user-info card is byte-identical."""

    def test_unauthenticated_redirects_to_login(self, client):
        """Unauthenticated /profile redirects to /login (DoD: still auth-gated)."""
        resp = client.get("/profile")
        # Flask test client follows no redirect automatically.
        assert resp.status_code == 302
        assert "/login" in resp.headers.get("Location", "")

    def test_user_info_card_identical_with_and_without_filter(
        self, logged_in_client, known_expenses
    ):
        """User-info card (name, email, member-since) byte-identical with or without filter (DoD)."""
        plain = logged_in_client.get("/profile").get_data(as_text=True)
        filtered = logged_in_client.get(
            "/profile", query_string={"range": "last_month"}
        ).get_data(as_text=True)
        assert _user_info_block(plain) == _user_info_block(filtered)
        assert _user_info_block(plain) != ""


# ---------------------------------------------------------------------------
# Section 4 — Template / form assertions (DoD: filter bar rehydrates, banner, reset).
# ---------------------------------------------------------------------------

class TestTemplateAndForm:
    """Template-level assertions: select reflects active filter, banner, reset link."""

    def test_select_reflects_active_filter(self, logged_in_client, known_expenses):
        """The <select> reflects the active filter — the right option has `selected`."""
        for preset, expected in [
            ("this_month", "this_month"),
            ("last_month", "last_month"),
            ("last_3_months", "last_3_months"),
            ("last_6_months", "last_6_months"),
            ("custom", "custom"),
        ]:
            resp = logged_in_client.get(
                "/profile",
                query_string={"range": preset, "from": "2026-01-01", "to": "2026-01-31"}
                if preset == "custom"
                else {"range": preset},
            )
            assert resp.status_code == 200
            html = resp.get_data(as_text=True)
            assert _selected_option_value(html) == expected, (
                f"preset {preset} should select {expected!r}"
            )

    def test_custom_date_inputs_rehydrate_for_custom_only(
        self, logged_in_client, known_expenses
    ):
        """Date inputs rehydrate only when the active filter is custom."""
        # Custom: inputs should show the values.
        custom_html = logged_in_client.get(
            "/profile",
            query_string={"range": "custom", "from": "2025-01-10", "to": "2025-01-20"},
        ).get_data(as_text=True)
        assert _date_input_value(custom_html, "from") == "2025-01-10"
        assert _date_input_value(custom_html, "to") == "2025-01-20"
        # Non-custom: inputs should be blank.
        preset_html = logged_in_client.get(
            "/profile", query_string={"range": "this_month"}
        ).get_data(as_text=True)
        assert _date_input_value(preset_html, "from") == ""
        assert _date_input_value(preset_html, "to") == ""
        # Lifetime: inputs should be blank.
        lifetime_html = logged_in_client.get("/profile").get_data(as_text=True)
        assert _date_input_value(lifetime_html, "from") == ""
        assert _date_input_value(lifetime_html, "to") == ""

    def test_banner_present_when_filtered_absent_for_lifetime(
        self, logged_in_client, known_expenses
    ):
        """The 'Showing X — Y · N transactions' banner appears for filters, not lifetime."""
        # Lifetime: no banner.
        plain = logged_in_client.get("/profile").get_data(as_text=True)
        assert _banner_text(plain) is None
        # Filtered: banner present and contains count.
        filtered = logged_in_client.get(
            "/profile", query_string={"range": "this_month"}
        ).get_data(as_text=True)
        banner = _banner_text(filtered)
        assert banner is not None
        assert "transactions" in banner
        assert "1" in banner  # 1 expense in this month

    def test_reset_link_points_to_profile_with_no_query(
        self, logged_in_client, known_expenses
    ):
        """The Reset link points to /profile with no query string."""
        filtered = logged_in_client.get(
            "/profile", query_string={"range": "last_month"}
        ).get_data(as_text=True)
        reset = _reset_href(filtered)
        assert reset is not None
        # url_for('profile') → /profile (or /profile?...)
        assert reset.split("?")[0] == "/profile"
        assert "?" not in reset


# ---------------------------------------------------------------------------
# Section 5 — DB helper unit tests (DoD: SQL aggregations respect the date range).
# ---------------------------------------------------------------------------

class TestDbHelpers:
    """Black-box unit tests of the DB helpers with date_from/date_to arguments."""

    def test_get_total_spent_empty_range_returns_zero(self, isolated_db):
        """get_total_spent returns 0.0 for an empty range."""
        # No expenses inserted.
        total = db_module.get_total_spent(isolated_db["user_id"], "2020-01-01", "2020-01-31")
        assert total == 0.0

    def test_get_top_category_empty_range_returns_none(self, isolated_db):
        """get_top_category returns None for an empty range."""
        top = db_module.get_top_category(isolated_db["user_id"], "2020-01-01", "2020-01-31")
        assert top is None

    def test_count_expenses_for_user_empty_range_returns_zero(self, isolated_db):
        """count_expenses_for_user returns 0 for an empty range."""
        count = db_module.count_expenses_for_user(
            isolated_db["user_id"], "2020-01-01", "2020-01-31"
        )
        assert count == 0

    def test_get_category_breakdown_empty_range_returns_empty_list(self, isolated_db):
        """get_category_breakdown returns [] for an empty range."""
        breakdown = db_module.get_category_breakdown(
            isolated_db["user_id"], "2020-01-01", "2020-01-31"
        )
        assert breakdown == []

    def test_helpers_with_none_args_preserve_lifetime_behaviour(self, isolated_db):
        """With date_from=None, date_to=None the helpers behave as before (lifetime)."""
        user_id = isolated_db["user_id"]
        # Insert two expenses with known amounts.
        with db_module.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO expenses (user_id, amount, category, date, description) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, 10.0, "Food", "2024-01-15", "x"),
            )
            cursor.execute(
                "INSERT INTO expenses (user_id, amount, category, date, description) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, 20.0, "Bills", "2024-02-15", "y"),
            )
        # Lifetime total = 30, count = 2.
        assert db_module.get_total_spent(user_id) == 30.0
        assert db_module.count_expenses_for_user(user_id) == 2
        # Top category is the one with the larger total ("Bills" = 20).
        assert db_module.get_top_category(user_id) == "Bills"
        breakdown = db_module.get_category_breakdown(user_id)
        assert [b[0] for b in breakdown] == ["Bills", "Food"]
        # Percentages sum to exactly 100.
        assert sum(b[2] for b in breakdown) == 100

    def test_get_expenses_for_user_filters_and_orders_correctly(self, isolated_db):
        """get_expenses_for_user returns only in-range rows, ordered date DESC, id DESC, capped at limit."""
        user_id = isolated_db["user_id"]
        # Insert expenses on both sides of the range.
        with db_module.get_db() as conn:
            cursor = conn.cursor()
            for d, amt in [
                ("2024-01-05", 1.0),
                ("2024-02-10", 2.0),
                ("2024-02-20", 3.0),
                ("2024-03-01", 4.0),
                ("2024-03-15", 5.0),
            ]:
                cursor.execute(
                    "INSERT INTO expenses (user_id, amount, category, date, description) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (user_id, amt, "X", d, d),
                )
        # Filter to Feb 2024 only.
        rows = db_module.get_expenses_for_user(
            user_id, limit=10, date_from="2024-02-01", date_to="2024-02-29"
        )
        dates = [r["date"] for r in rows]
        assert dates == ["2024-02-20", "2024-02-10"]
        # Limit honoured.
        capped = db_module.get_expenses_for_user(
            user_id, limit=1, date_from="2024-03-01", date_to="2024-03-31"
        )
        assert len(capped) == 1
        assert capped[0]["date"] == "2024-03-15"
