"""Shared fixtures for the Spendly test suite.

Isolation strategy
-------------------
``app.py`` runs ``init_db()`` and ``seed_db()`` against ``database.db.DB_PATH``
the moment it is imported (module-level code, not inside ``if __name__``).
To guarantee no test ever touches the developer's real ``expense_tracker.db``,
``DB_PATH`` is redirected to a throwaway temp file *before* ``app`` is
imported for the first time, below.

Every individual test then gets its own fresh, empty database via the
``db_path`` fixture, which repoints ``database.db.DB_PATH`` at a new
``tmp_path`` file and creates the schema with ``init_db()``. Because
``get_db()`` reads the ``DB_PATH`` module global at call time (not at import
time), this is enough to isolate every request the test client makes —
including the ones inside ``profile()`` — without editing any source file.
No test seeds data via ``seed_db()``; each test inserts exactly the rows it
needs through the ``make_user`` / ``make_expense`` fixtures below, dated
relative to ``date.today()`` so the suite does not rot next month.
"""
import os
import sys
import tempfile

import pytest
from werkzeug.security import generate_password_hash

# Make sure the project root (this file's parent directory) is importable
# regardless of the directory pytest is invoked from.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import database.db as db_module  # noqa: E402

# Redirect DB_PATH *before* app.py's module-level init_db()/seed_db() run,
# so that one-time bootstrap never reaches the real database file.
_bootstrap_fd, _bootstrap_path = tempfile.mkstemp(suffix=".db")
os.close(_bootstrap_fd)
db_module.DB_PATH = _bootstrap_path

import app as flask_app_module  # noqa: E402  (import must follow the DB_PATH patch)


@pytest.fixture
def db_path(monkeypatch, tmp_path):
    """Point every get_db() call at a fresh, empty temporary database."""
    path = str(tmp_path / "test_spendly.db")
    monkeypatch.setattr(db_module, "DB_PATH", path)
    db_module.init_db()
    yield path


@pytest.fixture
def app(db_path):
    flask_app_module.app.config.update(
        {"TESTING": True, "SECRET_KEY": "test-secret"}
    )
    yield flask_app_module.app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def make_user(db_path):
    """Factory fixture: insert a user row directly, bypassing /register."""

    def _make_user(email="user@example.com", name="Test User", password="testpass123"):
        conn = db_module.get_db()
        try:
            with conn:
                cursor = conn.execute(
                    "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                    (name, email, generate_password_hash(password)),
                )
            return cursor.lastrowid
        finally:
            conn.close()

    return _make_user


@pytest.fixture
def make_expense(db_path):
    """Factory fixture: insert an expense row directly for a given user_id."""

    def _make_expense(user_id, amount, category, iso_date, description=""):
        conn = db_module.get_db()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO expenses (user_id, amount, category, date, description) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (user_id, amount, category, iso_date, description),
                )
        finally:
            conn.close()

    return _make_expense


@pytest.fixture
def login_as():
    """Factory fixture: sign a test client in by writing user_id into the
    session directly — no real credentials, no POST to /login."""

    def _login_as(client_, user_id):
        with client_.session_transaction() as sess:
            sess["user_id"] = user_id

    return _login_as
