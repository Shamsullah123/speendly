"""Tests for Spendly Step 6 — the /profile date range filter.

Spec: .claude/specs/06-profile-date-filter.md

Two layers are exercised:

1. ``resolve_range(args)`` directly. The spec deliberately has this helper
   take a plain args mapping rather than reading ``request.args`` itself,
   "so the date arithmetic can be exercised without a request context" —
   these tests take it up on that.
2. ``GET /profile`` through the Flask test client, for auth guarding,
   per-user scoping, validation fallbacks, template coherence and the
   empty-state copy.

Every test gets a fresh, empty temporary SQLite database (see
``tests/conftest.py``) seeded only with the rows that test itself inserts,
dated relative to ``date.today()``. Nothing here reads or writes the
developer's real ``expense_tracker.db``, and no row survives past the test
that created it.
"""
from datetime import date, timedelta

import pytest

from app import BAD_RANGE, RANGE_PRESETS, resolve_range

TODAY = date.today()


def iso(d):
    return d.isoformat()


def rupees(value):
    """Mirror app.py's `rupees` currency filter so expected totals are built
    the same way the template renders them, rather than hardcoding strings."""
    return f"₹{float(value):,.0f}"


# ----------------------------------------------------------------------- #
# resolve_range() — pure function, no request/DB required                  #
# ----------------------------------------------------------------------- #

class TestResolveRangePresets:
    """Spec 'Files to change > app.py': the four fixed presets' date math."""

    def test_month_preset_spans_first_of_month_through_today(self):
        start, end, label, active, error = resolve_range({"range": "month"})
        assert active == "month"
        assert start == date(TODAY.year, TODAY.month, 1).isoformat()
        assert end == TODAY.isoformat()
        assert error is None

    def test_30d_preset_spans_29_days_before_through_today(self):
        start, end, label, active, error = resolve_range({"range": "30d"})
        assert active == "30d"
        assert start == (TODAY - timedelta(days=29)).isoformat(), (
            "spec: '30d means today and the 29 days before it' — 30 days "
            "counting today, not 31"
        )
        assert end == TODAY.isoformat()
        assert error is None

    def test_year_preset_spans_jan_1_through_today(self):
        start, end, label, active, error = resolve_range({"range": "year"})
        assert active == "year"
        assert start == date(TODAY.year, 1, 1).isoformat()
        assert end == TODAY.isoformat()
        assert error is None

    def test_all_preset_has_no_bounds(self):
        start, end, label, active, error = resolve_range({"range": "all"})
        assert (start, end) == (None, None)
        assert active == "all"
        assert label == "All time"
        assert error is None

    def test_missing_range_arg_behaves_exactly_like_explicit_all(self):
        """Spec: '/profile with no parameters must behave exactly as it does
        today (all time).' resolve_range({}) is the no-query-string case."""
        assert resolve_range({}) == resolve_range({"range": "all"})


class TestResolveRangeCustom:
    """Spec: custom bounds are inclusive on both ends, and either bound may
    be omitted to leave that side open."""

    def test_custom_both_bounds_are_inclusive_iso_strings(self):
        start, end, label, active, error = resolve_range(
            {"range": "custom", "from": "2026-08-01", "to": "2026-08-03"}
        )
        assert (start, end) == ("2026-08-01", "2026-08-03")
        assert active == "custom"
        assert error is None

    def test_custom_open_start_leaves_start_none(self):
        start, end, label, active, error = resolve_range(
            {"range": "custom", "to": "2026-08-03"}
        )
        assert start is None
        assert end == "2026-08-03"
        assert error is None

    def test_custom_open_end_leaves_end_none(self):
        start, end, label, active, error = resolve_range(
            {"range": "custom", "from": "2026-08-01"}
        )
        assert start == "2026-08-01"
        assert end is None
        assert error is None

    def test_custom_unparseable_date_falls_back_to_all_with_error(self):
        start, end, label, active, error = resolve_range(
            {"range": "custom", "from": "not-a-date", "to": "2026-08-03"}
        )
        assert (start, end) == (None, None), "a bad range must fall back to all time"
        assert error is not None
        assert label == "All time"

    def test_custom_from_after_to_falls_back_to_all_with_error(self):
        start, end, label, active, error = resolve_range(
            {"range": "custom", "from": "2026-08-31", "to": "2026-08-01"}
        )
        assert (start, end) == (None, None)
        assert error is not None

    def test_custom_out_of_calendar_date_falls_back_to_all_with_error(self):
        """2026-13-45 is not a real calendar date; strptime must reject it
        rather than silently clamping it or raising past resolve_range."""
        start, end, label, active, error = resolve_range(
            {"range": "custom", "from": "2026-13-45"}
        )
        assert (start, end) == (None, None)
        assert error is not None


class TestResolveRangeWhitelist:
    """Spec: 'Whitelist the preset before branching on it.'"""

    def test_unrecognised_range_value_falls_back_to_all(self):
        start, end, label, active, error = resolve_range({"range": "decade"})
        assert active == "all"
        assert (start, end) == (None, None)
        assert label == "All time"

    def test_sql_injection_like_range_value_falls_back_to_all(self):
        start, end, label, active, error = resolve_range(
            {"range": "';DROP TABLE expenses;--"}
        )
        assert active == "all", "range must be checked against a fixed set, never branched on raw"
        assert (start, end) == (None, None)

    @pytest.mark.parametrize("value", RANGE_PRESETS)
    def test_every_whitelisted_preset_is_accepted_as_active(self, value):
        _, _, _, active, _ = resolve_range({"range": value})
        assert active == value


class TestResolveRangeLabel:
    """Spec: label 'built here too, using the existing fmt_date formatting
    style — the template should not be doing date arithmetic.'"""

    def test_label_all_time(self):
        _, _, label, _, _ = resolve_range({"range": "all"})
        assert label == "All time"

    def test_label_custom_both_bounds_joins_the_two_dates(self):
        _, _, label, _, _ = resolve_range(
            {"range": "custom", "from": "2026-08-01", "to": "2026-08-03"}
        )
        assert "–" in label  # en dash joining the two formatted dates
        assert label.count("–") == 1

    def test_label_custom_open_start_says_from(self):
        _, _, label, _, _ = resolve_range({"range": "custom", "to": "2026-08-03"})
        assert label.startswith("From ")

    def test_label_custom_open_end_says_up_to(self):
        _, _, label, _, _ = resolve_range({"range": "custom", "from": "2026-08-01"})
        assert label.startswith("Up to ")


# ----------------------------------------------------------------------- #
# GET /profile — auth guard                                                #
# ----------------------------------------------------------------------- #

class TestAuthGuard:
    def test_profile_with_range_filter_redirects_to_login_when_logged_out(self, client):
        response = client.get("/profile?range=month")
        assert response.status_code == 302, "an unauthenticated request must not reach the view"
        assert "/login" in response.headers["Location"], (
            "the query string must not bypass @login_required"
        )


# ----------------------------------------------------------------------- #
# GET /profile — happy path per preset                                     #
# ----------------------------------------------------------------------- #

class TestPresetHappyPaths:
    def test_bare_profile_and_explicit_all_render_identically(
        self, client, make_user, make_expense, login_as
    ):
        user_id = make_user()
        make_expense(user_id, 100, "Food", iso(TODAY), "only expense")
        login_as(client, user_id)

        bare = client.get("/profile")
        explicit_all = client.get("/profile?range=all")

        assert bare.status_code == 200
        assert explicit_all.status_code == 200
        assert bare.data == explicit_all.data, (
            "spec: '/profile with no parameters must behave exactly as it does today (all time)'"
        )

    def test_range_month_excludes_an_expense_from_over_a_year_ago(
        self, client, make_user, make_expense, login_as
    ):
        user_id = make_user()
        make_expense(user_id, 100, "Food", iso(TODAY), "in current month")
        outside = TODAY - timedelta(days=400)  # unambiguously outside this month
        make_expense(user_id, 999, "Bills", iso(outside), "way outside the month")
        login_as(client, user_id)

        resp = client.get("/profile?range=month")

        assert resp.status_code == 200
        assert b"in current month" in resp.data
        assert b"way outside the month" not in resp.data

    def test_range_30d_boundary_29_days_included_30_days_excluded(
        self, client, make_user, make_expense, login_as
    ):
        user_id = make_user()
        make_expense(
            user_id, 50, "Food", iso(TODAY - timedelta(days=29)),
            "29 days ago boundary included",
        )
        make_expense(
            user_id, 999, "Bills", iso(TODAY - timedelta(days=30)),
            "30 days ago must be excluded",
        )
        login_as(client, user_id)

        resp = client.get("/profile?range=30d")

        assert resp.status_code == 200
        assert b"29 days ago boundary included" in resp.data
        assert b"30 days ago must be excluded" not in resp.data

    def test_range_year_boundary_jan_1_included_prior_dec_31_excluded(
        self, client, make_user, make_expense, login_as
    ):
        user_id = make_user()
        make_expense(
            user_id, 75, "Food", iso(date(TODAY.year, 1, 1)),
            "jan 1 this year boundary included",
        )
        make_expense(
            user_id, 999, "Bills", iso(date(TODAY.year - 1, 12, 31)),
            "last day of prior year excluded",
        )
        login_as(client, user_id)

        resp = client.get("/profile?range=year")

        assert resp.status_code == 200
        assert b"jan 1 this year boundary included" in resp.data
        assert b"last day of prior year excluded" not in resp.data

    def test_range_all_includes_expenses_from_every_era(
        self, client, make_user, make_expense, login_as
    ):
        user_id = make_user()
        make_expense(user_id, 10, "Food", "2001-01-01", "very old expense")
        make_expense(user_id, 20, "Bills", iso(TODAY), "todays expense")
        login_as(client, user_id)

        resp = client.get("/profile?range=all")

        assert resp.status_code == 200
        assert b"very old expense" in resp.data
        assert b"todays expense" in resp.data


# ----------------------------------------------------------------------- #
# GET /profile — custom range                                              #
# ----------------------------------------------------------------------- #

class TestCustomRange:
    def test_custom_range_inclusive_on_both_endpoints(
        self, client, make_user, make_expense, login_as
    ):
        user_id = make_user()
        make_expense(user_id, 10, "Food", "2026-08-01", "on start boundary")
        make_expense(user_id, 20, "Food", "2026-08-02", "middle of range")
        make_expense(user_id, 30, "Food", "2026-08-03", "on end boundary")
        make_expense(user_id, 40, "Food", "2026-07-31", "day before start excluded")
        make_expense(user_id, 50, "Food", "2026-08-04", "day after end excluded")
        login_as(client, user_id)

        resp = client.get("/profile?range=custom&from=2026-08-01&to=2026-08-03")

        assert resp.status_code == 200
        assert b"on start boundary" in resp.data
        assert b"middle of range" in resp.data
        assert b"on end boundary" in resp.data
        assert b"day before start excluded" not in resp.data
        assert b"day after end excluded" not in resp.data

    def test_custom_range_open_ended_from_only(
        self, client, make_user, make_expense, login_as
    ):
        user_id = make_user()
        make_expense(user_id, 10, "Food", "2026-08-01", "on the from date")
        make_expense(user_id, 20, "Food", "2026-12-25", "well after from no to bound")
        make_expense(user_id, 30, "Food", "2026-07-31", "before from excluded")
        login_as(client, user_id)

        resp = client.get("/profile?range=custom&from=2026-08-01")

        assert resp.status_code == 200
        assert b"on the from date" in resp.data
        assert b"well after from no to bound" in resp.data
        assert b"before from excluded" not in resp.data

    def test_custom_range_open_ended_to_only(
        self, client, make_user, make_expense, login_as
    ):
        user_id = make_user()
        make_expense(user_id, 10, "Food", "2026-08-03", "on the to date")
        make_expense(user_id, 20, "Food", "2001-01-01", "well before to no from bound")
        make_expense(user_id, 30, "Food", "2026-08-04", "after to excluded")
        login_as(client, user_id)

        resp = client.get("/profile?range=custom&to=2026-08-03")

        assert resp.status_code == 200
        assert b"on the to date" in resp.data
        assert b"well before to no from bound" in resp.data
        assert b"after to excluded" not in resp.data

    def test_custom_range_dates_are_echoed_back_prefilled(self, client, make_user, login_as):
        user_id = make_user()
        login_as(client, user_id)

        resp = client.get("/profile?range=custom&from=2026-08-01&to=2026-08-03")

        assert resp.status_code == 200
        assert b'value="2026-08-01"' in resp.data, "the from input must echo the submitted date"
        assert b'value="2026-08-03"' in resp.data, "the to input must echo the submitted date"


# ----------------------------------------------------------------------- #
# GET /profile — validation errors never 500                               #
# ----------------------------------------------------------------------- #

class TestValidationErrors:
    def test_reversed_custom_range_returns_200_with_message_and_falls_back_to_all_time(
        self, client, make_user, make_expense, login_as
    ):
        user_id = make_user()
        make_expense(user_id, 10, "Food", "2001-01-01", "reappears under all time fallback")
        login_as(client, user_id)

        resp = client.get("/profile?range=custom&from=2026-08-31&to=2026-08-01")

        assert resp.status_code == 200, "a bad range must render the page, never 500"
        assert BAD_RANGE.encode("utf-8") in resp.data
        assert b"reappears under all time fallback" in resp.data, (
            "on error the view falls back to the all-time window"
        )

    def test_unparseable_custom_date_returns_200_with_message(self, client, make_user, login_as):
        user_id = make_user()
        login_as(client, user_id)

        resp = client.get("/profile?range=custom&from=not-a-date")

        assert resp.status_code == 200
        assert BAD_RANGE.encode("utf-8") in resp.data

    def test_out_of_calendar_custom_date_returns_200_not_500(self, client, make_user, login_as):
        user_id = make_user()
        login_as(client, user_id)

        resp = client.get("/profile?range=custom&from=2026-13-45")

        assert resp.status_code == 200
        assert BAD_RANGE.encode("utf-8") in resp.data

    def test_unrecognised_range_value_falls_back_to_all_time(
        self, client, make_user, make_expense, login_as
    ):
        user_id = make_user()
        make_expense(user_id, 10, "Food", "2001-01-01", "ancient row visible under all time")
        login_as(client, user_id)

        resp = client.get("/profile?range=9999")

        assert resp.status_code == 200
        assert b"All time" in resp.data
        assert b"ancient row visible under all time" in resp.data

    def test_rejected_custom_range_still_echoes_raw_input_so_form_stays_editable(
        self, client, make_user, login_as
    ):
        user_id = make_user()
        login_as(client, user_id)

        resp = client.get("/profile?range=custom&from=2026-08-31&to=2026-08-01")

        assert resp.status_code == 200
        assert b'value="2026-08-31"' in resp.data
        assert b'value="2026-08-01"' in resp.data


# ----------------------------------------------------------------------- #
# GET /profile — preset whitelist against hostile input                    #
# ----------------------------------------------------------------------- #

class TestPresetWhitelist:
    def test_hostile_range_value_degrades_to_all_time_and_leaves_table_intact(
        self, client, make_user, make_expense, login_as
    ):
        import database.db as db_module

        user_id = make_user()
        make_expense(user_id, 10, "Food", "2001-01-01", "row that must survive")
        login_as(client, user_id)

        resp = client.get("/profile?range=" + "';DROP TABLE expenses;--")

        assert resp.status_code == 200, "a hostile range value must not crash the request"
        assert b"All time" in resp.data
        assert b"row that must survive" in resp.data

        conn = db_module.get_db()
        try:
            count = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
        finally:
            conn.close()
        assert count == 1, "the expenses table must still exist and hold its row"


# ----------------------------------------------------------------------- #
# GET /profile — per-user scoping                                          #
# ----------------------------------------------------------------------- #

class TestPerUserScoping:
    def test_same_range_shows_only_the_signed_in_users_own_rows(
        self, client, make_user, make_expense, login_as
    ):
        alice_id = make_user(email="alice@example.com", name="Alice")
        bob_id = make_user(email="bob@example.com", name="Bob")

        make_expense(alice_id, 111, "Food", iso(TODAY), "alice-only-expense")
        make_expense(bob_id, 222, "Bills", iso(TODAY), "bob-only-expense")

        login_as(client, alice_id)
        alice_resp = client.get("/profile?range=month")
        assert alice_resp.status_code == 200
        assert b"alice-only-expense" in alice_resp.data
        assert b"bob-only-expense" not in alice_resp.data, (
            "spec: the filter narrows a user's own rows; it never widens past their own user_id"
        )

        login_as(client, bob_id)
        bob_resp = client.get("/profile?range=month")
        assert bob_resp.status_code == 200
        assert b"bob-only-expense" in bob_resp.data
        assert b"alice-only-expense" not in bob_resp.data


# ----------------------------------------------------------------------- #
# GET /profile — stats, table and bars must agree on one window            #
# ----------------------------------------------------------------------- #

class TestCoherence:
    def test_stats_transactions_and_category_bars_all_describe_the_same_window(
        self, client, make_user, make_expense, login_as
    ):
        user_id = make_user()
        make_expense(user_id, 100, "Groceries", iso(TODAY), "in-window-groceries")
        make_expense(user_id, 150, "Travel", iso(TODAY), "in-window-travel")
        outside = TODAY - timedelta(days=400)
        make_expense(user_id, 999, "AncientSpending", iso(outside), "out-of-window-ancient")
        login_as(client, user_id)

        resp = client.get("/profile?range=month")
        text = resp.data.decode("utf-8")

        assert resp.status_code == 200
        # Table: only in-window rows
        assert "in-window-groceries" in text
        assert "in-window-travel" in text
        assert "out-of-window-ancient" not in text
        # Bars: only in-window categories
        assert "Groceries" in text
        assert "Travel" in text
        assert "AncientSpending" not in text
        # Stats: total spent is the sum of only the in-window rows (100 + 150)
        assert rupees(250) in text, (
            "summary.total_spent must equal the sum of rows inside the filtered window, "
            "not lifetime spend — stats, table and bars must not drift apart"
        )


# ----------------------------------------------------------------------- #
# GET /profile — empty states                                              #
# ----------------------------------------------------------------------- #

class TestEmptyStates:
    def test_expenses_exist_but_none_in_range_shows_filtered_copy_and_clear_link(
        self, client, make_user, make_expense, login_as
    ):
        user_id = make_user()
        outside = TODAY - timedelta(days=400)
        make_expense(user_id, 50, "Food", iso(outside), "only expense outside this months window")
        login_as(client, user_id)

        resp = client.get("/profile?range=month")
        text = resp.data.decode("utf-8")

        assert resp.status_code == 200
        assert "No expenses in this range" in text, (
            "an account with expenses but none in the selected window needs filtered "
            "copy, not the generic empty-account message"
        )
        assert 'href="/profile"' in text, (
            "the filtered empty state must include a link back to plain /profile to clear it"
        )

    def test_account_with_no_expenses_at_all_keeps_original_empty_copy(
        self, client, make_user, login_as
    ):
        user_id = make_user()
        login_as(client, user_id)

        resp = client.get("/profile")
        text = resp.data.decode("utf-8")

        assert resp.status_code == 200
        assert "No expenses yet." in text
        assert "No expenses in this range" not in text, (
            "a genuinely empty account is not the same case as a filtered-out one"
        )
