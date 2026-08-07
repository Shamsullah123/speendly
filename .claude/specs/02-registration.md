# Spec: Registration

## Overview

Make the existing registration form actually work. `templates/register.html` already POSTs to
`/register`, but `app.py` registers that route GET-only, so submitting the form returns **405
Method Not Allowed** today — this is the gap CLAUDE.md names as Step 2's work. This step adds POST
handling: validate the submitted name, email and password; reject duplicate emails against the
`users` table's UNIQUE constraint; hash the password with werkzeug; insert the row; and redirect to
the sign-in page. It is the first feature to write to the database created in Step 1, and it is
what makes every later step (login, profile, expenses) have a real account to hang off.

Sessions are **not** part of this step — a successful registration does not log the user in, it
sends them to `/login`. That belongs to Step 3.

## Depends on

- **Step 1 — Database Setup** (complete). Requires `get_db()` and the `users` table from
  `database/db.py`, including the UNIQUE constraint on `email`.

Nothing else. `/login` remains GET-only after this step and will still return 405 on submit; that
is its own step's work and must not be picked up here.

## Routes

- `GET /register` — render the empty registration form — public *(exists; unchanged behaviour)*
- `POST /register` — validate and create the account, then redirect to `/login` — public *(new)*

Both are served by the existing `register()` view, widened to
`@app.route("/register", methods=["GET", "POST"])`. No other route changes.

## Database changes

**No database changes.** The `users` table already provides everything this step needs:

| Column | Supplied by |
| --- | --- |
| `id` | autoincrement |
| `name` | form field `name` |
| `email` | form field `email`, normalised |
| `password_hash` | `generate_password_hash(password)` |
| `created_at` | column default `datetime('now')` |

`database/db.py` is not modified.

## Templates

- **Create:** none.
- **Modify:** `templates/register.html` — repopulate the name and email inputs on a failed submit
  (`value="{{ name or '' }}"`, `value="{{ email or '' }}"`) so a rejected user is not made to retype
  everything. The `{% if error %}` block at lines 16–18 already exists and needs no change; the view
  passes `error` into it. Password is never echoed back.

`.auth-error` is already styled in `static/css/style.css:468`, so **no CSS changes are needed**.

## Files to change

- `app.py` — add `redirect`, `request`, `url_for` to the `flask` import; add
  `generate_password_hash` from `werkzeug.security`; widen the `/register` route to accept POST and
  implement the handler.
- `templates/register.html` — sticky `name` and `email` values as described above.
- `CLAUDE.md` — update the "Known gaps" bullet: registration now works; note that `/login` POST is
  still 405 and remains Step 3's work.

## Files to create

None.

## New dependencies

**No new dependencies.** `flask==3.1.3` and `werkzeug==3.1.6` are already in `requirements.txt`,
and `werkzeug.security.generate_password_hash` is already used by `database/db.py:76`.

## Rules for implementation

- **No SQLAlchemy or ORMs** — `sqlite3` via `get_db()` only.
- **Parameterised queries only.** Never build SQL with f-strings, `%`, or `.format()`.
- **Passwords hashed with werkzeug** — `generate_password_hash(password)`. Never store, log, or
  echo the plaintext password, and never pass it back into the template.
- **Use CSS variables — never hardcode hex values.** (No CSS is expected here; if any is added, it
  goes in the existing Auth pages banner section of `static/css/style.css` and uses `--ink*`,
  `--paper*`, `--accent*`, `--radius-*`.)
- **All templates extend `base.html`.** `register.html` already does; do not change that.
- Open the connection with `get_db()` and close it in a `finally` (or use `with conn:` for the
  write) so a validation failure cannot leak a handle.
- Validation happens **server-side** regardless of the HTML `required` attributes — those are a
  convenience, not a control. Rules:
  - `name` — required, stripped, non-empty
  - `email` — required, stripped, lowercased before both the uniqueness check and the insert
  - `password` — required, minimum 8 characters (the form's placeholder already promises this)
- Duplicate email must be reported as a friendly message, not a traceback. Prefer catching
  `sqlite3.IntegrityError` around the insert over a check-then-insert, or do both — a prior
  `SELECT` alone is a race.
- One error message at a time via the existing `error` template variable. Do **not** introduce
  `flash()` — it needs `app.secret_key` and session wiring, which is Step 3.
- On success: `redirect(url_for("login"))`. Do not set any session key.
- Do not touch the placeholder routes for Steps 3, 4, 7, 8 and 9, and do not implement `/login`.

## Definition of done

Verify with the test client per CLAUDE.md (`.\venv\Scripts\python.exe`), not a browser:

- [ ] `GET /register` still returns 200 and renders the form.
- [ ] `POST /register` with a valid new name/email/password returns a 302 redirect to `/login`
      (no longer 405).
- [ ] After that POST, a row exists in `users` with the submitted name and the lowercased email.
- [ ] The stored `password_hash` is **not** the plaintext password, and
      `check_password_hash(row["password_hash"], password)` returns `True`.
- [ ] `created_at` is populated by the column default.
- [ ] Re-POSTing the **same email** returns 200 (re-rendered form, not a redirect), shows an
      "already registered" style message in `.auth-error`, and adds **no** second row.
- [ ] Registering `DEMO@spendly.com` is rejected as a duplicate of the seeded `demo@spendly.com`.
- [ ] A password shorter than 8 characters is rejected with an error and creates no row.
- [ ] An empty `name` (e.g. `"   "`) is rejected with an error and creates no row.
- [ ] On any rejection, the re-rendered page contains the submitted name and email in the inputs
      and does **not** contain the submitted password anywhere in the response body.
- [ ] `/`, `/login`, `/terms`, `/privacy` still return 200; `POST /login` still returns 405.
- [ ] `.\venv\Scripts\python.exe app.py` starts with no errors.
