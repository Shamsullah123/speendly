import functools
import os
import sqlite3

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
            "SELECT id, name, email FROM users WHERE id = ?", (user_id,)
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


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/profile")
@login_required
def profile():
    return "Profile page — coming in Step 4"


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
