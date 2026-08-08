import functools
import os
import sqlite3
from datetime import date, datetime, timedelta

from flask import Flask, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import get_db, init_db, seed_db

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-not-for-production")

# Make sure the schema and demo data exist before any request is served.
with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Session helpers                                                     #
# ------------------------------------------------------------------ #

def login_required(view):
    """Send anonymous visitors to the sign-in page.

    functools.wraps keeps the wrapped function's name, which Flask uses as the
    endpoint — without it every decorated view would register as "wrapper".
    """
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def current_user():
    """The signed-in user's row, or None. Only the id lives in the session."""
    user_id = session.get("user_id")
    if user_id is None:
        return None

    conn = get_db()
    try:
        user = conn.execute(
            "SELECT id, name, email, created_at FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    finally:
        conn.close()

    if user is None:
        # The account was deleted out from under the session.
        session.clear()
    return user


@app.context_processor
def inject_current_user():
    """Make current_user available to every template, notably base.html."""
    return {"current_user": current_user()}


# ------------------------------------------------------------------ #
# Template filters                                                    #
# ------------------------------------------------------------------ #

@app.template_filter("fmt_date")
def fmt_date(value, fmt="%d %b %Y"):
    """Format a SQLite date string. Returns it unchanged if it won't parse."""
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value), pattern).strftime(fmt)
        except ValueError:
            continue
    return value


@app.template_filter("rupees")
def rupees(value):
    """₹ with thousands separators — the currency lives here, not in markup."""
    try:
        return f"₹{float(value):,.0f}"
    except (TypeError, ValueError):
        return value


# ------------------------------------------------------------------ #
# Date range filter                                                   #
# ------------------------------------------------------------------ #

# A whitelist, not a suggestion — ?range= arrives straight from the URL, so it
# is checked against this before anything branches on it.
RANGE_PRESETS = ("month", "30d", "year", "all", "custom")

BAD_RANGE = "Enter dates as YYYY-MM-DD, with the start date first."


def _parse_iso(value):
    """A YYYY-MM-DD string as a date, or None when blank. Raises on anything else."""
    value = (value or "").strip()
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def resolve_range(args):
    """Turn ?range/?from/?to into (start, end, label, active, error).

    start and end come back as ISO strings — the form expenses.date is stored in
    — or None for an open-ended bound. Nothing here raises: an unrecognised
    preset or an unparseable date falls back to the all-time window and reports
    a message, because a bad filter is not worth a 500.

    Takes the args mapping rather than reading the request itself, so the date
    arithmetic can be exercised without a request context.
    """
    active = args.get("range", "all")
    if active not in RANGE_PRESETS:
        active = "all"

    today = date.today()
    error = None

    if active == "month":
        start, end = date(today.year, today.month, 1), today
    elif active == "30d":
        # 29, not 30 — the window is 30 days counting today.
        start, end = today - timedelta(days=29), today
    elif active == "year":
        start, end = date(today.year, 1, 1), today
    elif active == "custom":
        # Either bound may be blank, which leaves that end open.
        try:
            start, end = _parse_iso(args.get("from")), _parse_iso(args.get("to"))
        except ValueError:
            start, end, error = None, None, BAD_RANGE
        else:
            if start and end and start > end:
                start, end, error = None, None, BAD_RANGE
    else:
        start, end = None, None

    start = start.isoformat() if start else None
    end = end.isoformat() if end else None

    # fmt_date is an ordinary function that also happens to be a template
    # filter, so the caption's dates read exactly like the table's.
    if start and end:
        label = f"{fmt_date(start)} – {fmt_date(end)}"
    elif start:
        label = f"From {fmt_date(start)}"
    elif end:
        label = f"Up to {fmt_date(end)}"
    else:
        label = "All time"

    return start, end, label, active, error


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    # Not stripped — spaces are legitimate password characters.
    password = request.form.get("password", "")

    def show_error(message):
        return render_template("register.html", error=message, name=name, email=email)

    if not name:
        return show_error("Please enter your name.")
    if not email:
        return show_error("Please enter your email address.")
    if len(password) < 8:
        return show_error("Password must be at least 8 characters.")

    conn = get_db()
    try:
        with conn:
            conn.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                (name, email, generate_password_hash(password)),
            )
    except sqlite3.IntegrityError:
        # The UNIQUE constraint on users.email — not a prior SELECT — is what
        # actually guarantees no duplicate account.
        return show_error("That email is already registered.")
    finally:
        conn.close()

    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip().lower()
    # Not stripped — spaces are legitimate password characters.
    password = request.form.get("password", "")

    def show_error(message):
        return render_template("login.html", error=message, email=email)

    # One message for every failure. Distinguishing "no such account" from
    # "wrong password" would let anyone test which emails are registered.
    incorrect = "Incorrect email or password."

    if not email or not password:
        return show_error(incorrect)

    conn = get_db()
    try:
        user = conn.execute(
            "SELECT id, password_hash FROM users WHERE email = ?", (email,)
        ).fetchone()
    finally:
        conn.close()

    if user is None or not check_password_hash(user["password_hash"], password):
        return show_error(incorrect)

    session.clear()
    session["user_id"] = user["id"]
    return redirect(url_for("profile"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/profile")
@login_required
def profile():
    """The signed-in user's own spending, read live from the expenses table.

    Account details still arrive via current_user, which the context processor
    injects into every template. Everything below is scoped to the session's
    user_id — an unscoped query here would show one account another's spending.

    The optional date range from the query string narrows all three queries
    together. Splitting them apart would let the stats describe one window while
    the bars below describe another.
    """
    user_id = session["user_id"]
    start, end, range_label, active_range, range_error = resolve_range(request.args)

    # Whether a bound actually applies, which is a different question from which
    # control looks selected. `range=custom` with both fields blank — or with
    # dates that failed validation — keeps active_range as "custom" while the
    # queries run unfiltered, so the empty states have to read this instead.
    filtered = bool(start or end)

    # Built once, from literals only. The user's dates never touch this string —
    # they go in through params as ? placeholders, same as user_id.
    where = "WHERE user_id = ?"
    params = [user_id]
    if start:
        where += " AND date >= ?"
        params.append(start)
    if end:
        where += " AND date <= ?"
        params.append(end)

    conn = get_db()
    try:
        # COALESCE because SUM over zero rows is NULL, which would reach the
        # rupees filter and render as an empty cell rather than ₹0.
        summary_row = conn.execute(
            "SELECT COUNT(*) AS transaction_count, "
            "COALESCE(SUM(amount), 0) AS total_spent "
            "FROM expenses " + where,
            params,
        ).fetchone()

        # date is ISO text, so a plain string sort is already chronological —
        # which is also what makes the >= / <= bounds above correct without any
        # date parsing in SQL. id DESC breaks ties, keeping same-day expenses
        # newest-first and in the same order on every refresh.
        transactions = conn.execute(
            "SELECT date, description, category, amount "
            "FROM expenses " + where + " "
            "ORDER BY date DESC, id DESC "
            "LIMIT 10",
            params,
        ).fetchall()

        category_rows = conn.execute(
            "SELECT category, SUM(amount) AS total "
            "FROM expenses " + where + " "
            "GROUP BY category "
            "ORDER BY total DESC",
            params,
        ).fetchall()
    finally:
        conn.close()

    # Bars are sized against the biggest category *in the window* rather than
    # against total spend, so the top one always fills its track whatever range
    # is selected. The query sorts descending,
    # so that is the first row. sqlite3.Row is immutable, which is why these
    # become dicts — percent is added after the fetch.
    largest = category_rows[0]["total"] if category_rows else 0
    categories = [
        {
            "name": row["category"],
            "total": row["total"],
            "percent": round(row["total"] / largest * 100) if largest else 0,
        }
        for row in category_rows
    ]

    summary = {
        "total_spent": summary_row["total_spent"],
        "transaction_count": summary_row["transaction_count"],
        # Free from the category query. Deriving it here rather than with a
        # fourth query means the stat can never disagree with the bars below it.
        # None when there is nothing to spend on yet; the template shows an em dash.
        "top_category": category_rows[0]["category"] if category_rows else None,
    }

    return render_template(
        "profile.html",
        summary=summary,
        transactions=transactions,
        categories=categories,
        range_label=range_label,
        active_range=active_range,
        filtered=filtered,
        # Echoed back raw so a rejected range stays editable rather than being
        # wiped. Jinja escapes it, and a value the date input cannot parse just
        # renders as an empty field.
        date_from=request.args.get("from", ""),
        date_to=request.args.get("to", ""),
        range_error=range_error,
    )


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
