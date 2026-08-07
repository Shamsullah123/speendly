# Spec: Login and Logout

## Overview

Give Spendly a session. `templates/login.html:20` POSTs to `/login`, but `app.py:62` registers that
route GET-only — submitting the sign-in form returns **405**, the last remaining gap named in
CLAUDE.md. This step adds POST handling that looks the user up by email, verifies the password with
`check_password_hash` against the hash Step 2 stored, and records `user_id` in Flask's signed
session cookie. It also turns `/logout` from a placeholder string into a real route that clears that
session, makes the navbar reflect who is signed in, and introduces a `login_required` decorator so
there is finally a meaningful distinction between a public and a logged-in page. Everything after
this — profile (Step 4) and the expense CRUD (Steps 7–9) — needs to know *which* user is asking, so
this is the step that makes the rest of the roadmap possible.

## Depends on

- **Step 1 — Database Setup** (complete): `get_db()` and the `users` table.
- **Step 2 — Registration** (complete): supplies accounts with a werkzeug hash in
  `users.password_hash`. Registration's success redirect already points at `/login`, so the two
  steps join up with no change to `register()`.

## Routes

- `GET /login` — render the sign-in form — public *(exists; unchanged behaviour)*
- `POST /login` — verify credentials, start the session, redirect to `/profile` — public *(new)*
- `GET /logout` — clear the session, redirect to `/` — public *(replaces the placeholder)*

`/profile` gains `@login_required` but keeps its route, its name and its placeholder body — it stays
Step 4's work. No other route changes; the expense placeholders for Steps 7–9 stay untouched and
unprotected.

`/logout` stays a `GET` so the navbar can link to it with a plain anchor. This is CSRF-able in
principle; the whole scaffold has no CSRF protection yet, and adding it for one route only would be
misleading. Out of scope, noted deliberately.

## Database changes

**No database changes.** `users` already holds `id`, `name`, `email` and `password_hash`
(`database/db.py:40-47`). Sessions live in Flask's signed cookie — no server-side session table.

## Templates

- **Create:** none.
- **Modify:**
  - `templates/login.html` — repopulate the email input on a failed submit
    (`value="{{ email or '' }}"`), matching what `register.html` does. The `{% if error %}` block at
    lines 16–18 already exists and needs no change. Password is never echoed back.
  - `templates/base.html` — make the navbar (lines 21-24) session-aware: when a user is signed in,
    show their name and a **Log out** link; otherwise keep today's **Sign in** / **Get started**
    pair unchanged.

## Files to change

- `app.py` — `import os`, `import functools`; add `session` to the `flask` import and
  `check_password_hash` to the `werkzeug.security` import; set `app.secret_key`; add the
  `login_required` decorator and a `current_user` context processor; implement `POST /login` and
  the real `/logout`; decorate `/profile`.
- `templates/login.html` — sticky email value.
- `templates/base.html` — conditional navbar.
- `static/css/style.css` — one new rule, `.nav-user`, in the existing **Navbar** banner section.
- `CLAUDE.md` — update "Known gaps" (the 405 is gone) and note the session/`current_user` pattern
  under Architecture.

## Files to create

None.

## New dependencies

**No new dependencies.** Flask's `session` and `werkzeug.security.check_password_hash` ship with
`flask==3.1.3` / `werkzeug==3.1.6`, both already in `requirements.txt`. `os` and `functools` are
standard library.

## Rules for implementation

- **No SQLAlchemy or ORMs** — `sqlite3` via `get_db()` only.
- **Parameterised queries only.** Never build SQL with f-strings, `%`, or `.format()`.
- **Passwords hashed with werkzeug** — verify with `check_password_hash(row["password_hash"],
  password)`. Never store, log, compare in plaintext, or echo the password back to the template.
- **Use CSS variables — never hardcode hex values.** The one new rule goes in the Navbar banner
  section of `static/css/style.css` and uses `--ink*` / `--accent*`.
- **All templates extend `base.html`.** `login.html` already does; do not change that.
- `app.secret_key = os.environ.get("SECRET_KEY", "<dev fallback>")` — confirmed with the user. Set
  it immediately after `app = Flask(__name__)`, before the `init_db()`/`seed_db()` block.
- **One generic failure message for both "no such email" and "wrong password"** — e.g. "Incorrect
  email or password." Telling them apart hands an attacker an account-enumeration oracle, and the
  registration form already reports duplicate emails, so this is the only place it can leak.
- Normalise the submitted email with `.strip().lower()` before the lookup — Step 2 stores emails
  lowercased, and SQLite's `=` is case-sensitive.
- Do **not** strip the password. Validate that email and password are non-empty before touching the
  database.
- `session.clear()` before setting `session["user_id"]`, so a stale session can never be inherited.
- Store **only** `user_id` in the session — never the name, email, or hash. The cookie is signed,
  not encrypted; anyone can read its contents.
- `logout()` uses `session.clear()` and redirects to `url_for("landing")`. It must not error when
  no one is logged in.
- The `current_user` context processor loads the row fresh per request from `session["user_id"]`.
  If the id is absent **or the row no longer exists**, expose `None` and clear the session — a
  deleted account must not leave a half-logged-in navbar.
- `login_required` wraps the view with `functools.wraps` (otherwise Flask sees duplicate endpoint
  names) and redirects anonymous visitors to `url_for("login")`.
- Every connection opened with `get_db()` is closed in a `finally`.
- Do not introduce `flash()`, "remember me", password reset, or CSRF tokens. Do not implement the
  profile page body or any expense route.

## Definition of done

Verify with the test client per CLAUDE.md (`.\venv\Scripts\python.exe`), not a browser. The seeded
`demo@spendly.com` / `demo123` account is the natural fixture.

- [ ] `GET /login` returns 200 and renders the form.
- [ ] `POST /login` with correct credentials returns **302** to `/profile` (no longer 405).
- [ ] After that POST the session cookie carries `user_id`, and a follow-up `GET /profile` in the
      same client returns 200 with the placeholder text.
- [ ] `POST /login` with `DEMO@SPENDLY.COM` (upper case) succeeds — email is normalised.
- [ ] A wrong password returns 200 with the error message and **no** session cookie set.
- [ ] An unknown email returns 200 with the **byte-identical** error message as the wrong-password
      case.
- [ ] On a failed login the re-rendered page contains the submitted email and does **not** contain
      the submitted password.
- [ ] `GET /profile` while logged out returns **302** to `/login`.
- [ ] `GET /logout` returns 302 to `/`, and `GET /profile` afterwards is back to redirecting to
      `/login`.
- [ ] `GET /logout` while already logged out still returns 302 and raises no error.
- [ ] The navbar on `/` contains "Sign in" when logged out, and the user's name plus a
      `href="/logout"` link when logged in — and never both.
- [ ] An account registered through `POST /register` can immediately log in with the same password.
- [ ] `/`, `/register`, `/terms`, `/privacy` still return 200 for anonymous visitors.
- [ ] `.\venv\Scripts\python.exe app.py` starts with no errors.
