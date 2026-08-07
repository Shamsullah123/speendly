"""SQLite helpers for Spendly — Step 1, Database Setup.

Exposes three functions:
    get_db()   — returns a SQLite connection with row_factory and foreign keys enabled
    init_db()  — creates all tables using CREATE TABLE IF NOT EXISTS
    seed_db()  — inserts sample data for development
"""

import os
import sqlite3

from werkzeug.security import generate_password_hash

# The .gitignore already reserves this filename at the repo root.
DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "expense_tracker.db",
)


def get_db():
    """Open a connection to the SQLite database.

    Rows come back as sqlite3.Row so they can be read by column name
    (row["email"]) instead of by position. Foreign key enforcement is off by
    default in SQLite and has to be switched on per connection.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create the tables if they do not exist yet. Safe to run repeatedly."""
    conn = get_db()
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT NOT NULL,
                email         TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at    TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS expenses (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                amount      REAL NOT NULL,
                category    TEXT NOT NULL,
                date        TEXT NOT NULL,
                description TEXT,
                created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            """
        )
    conn.close()


def seed_db():
    """Insert sample development data. Does nothing if users already exist."""
    conn = get_db()
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
        conn.close()
        return

    with conn:
        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Demo User", "demo@spendly.com", generate_password_hash("demo123")),
        )
        user_id = cursor.lastrowid

        # Covers every category in the fixed list, spread across the month.
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (user_id, 12.40, "Food", "2026-08-01", "Lunch at the deli"),
                (user_id, 2.75, "Transport", "2026-08-02", "Bus fare"),
                (user_id, 89.99, "Bills", "2026-08-02", "Electricity bill"),
                (user_id, 24.00, "Health", "2026-08-03", "Pharmacy prescription"),
                (user_id, 15.50, "Entertainment", "2026-08-04", "Cinema ticket"),
                (user_id, 62.30, "Shopping", "2026-08-05", "Running shoes"),
                (user_id, 9.00, "Other", "2026-08-05", "Charity donation"),
                (user_id, 34.20, "Food", "2026-08-06", "Weekly grocery shop"),
            ],
        )
    conn.close()


if __name__ == "__main__":
    init_db()
    seed_db()
    print(f"Database ready at {DB_PATH}")
