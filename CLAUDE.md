# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

Spendly — a personal expense tracker built with Flask, SQLite, and vanilla CSS/JS.

**This is a teaching scaffold, not a finished app.** The marketing/legal pages are fully built,
but the application logic is deliberately unimplemented and is meant to be filled in against a
numbered curriculum. Two things encode that curriculum:

- `app.py` — placeholder routes return literal strings naming their step
  (e.g. `"Add expense — coming in Step 7"`). Steps referenced so far: 3 (logout/sessions),
  4 (profile), 7 (add), 8 (edit), 9 (delete).
- `database/db.py` — **contains only comments**. It specifies three functions to write:
  `get_db()` (connection with `row_factory` + foreign keys on), `init_db()`
  (`CREATE TABLE IF NOT EXISTS`), `seed_db()` (sample data).

Do not "fix" the placeholder routes or stub file as if they were bugs.

## Commands

The virtualenv lives at `venv/` and is gitignored. Call its interpreter directly rather than
relying on the shell's `python` — on this machine a bare `python3` may resolve to a Microsoft
Store stub with no pip.

```powershell
# Run the dev server → http://127.0.0.1:5001  (note: 5001, not Flask's default 5000)
.\venv\Scripts\python.exe app.py

# Install/refresh dependencies
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

`app.run(debug=True)` means templates re-render per request — edit a template and just refresh,
no restart needed. Editing `app.py` triggers the auto-reloader.

### Checking routes without a browser

Faster and more reliable than launching the server, and the way route/template changes have
been verified in this repo:

```python
import app
c = app.app.test_client()
r = c.get("/terms")
print(r.status_code, b'href="/privacy"' in r.data)
```

Run such scripts from a scratch directory with `sys.path.insert(0, r"E:\projects\expense-tracker")`
at the top, or `cd` into the project first.

### Tests

`pytest` and `pytest-flask` are declared in `requirements.txt` but **no test suite exists yet** —
there is no `tests/` directory. Once tests are added:
`.\venv\Scripts\python.exe -m pytest` — single test: `... -m pytest tests/test_x.py::test_name`.

## Architecture

### Templates: everything inherits from `base.html`

`base.html` owns the `<head>`, the navbar, and **the footer**. Consequence worth internalising:
a request to change "the footer on the landing page" means editing `base.html`, not
`landing.html` — `landing.html` contains no footer markup. Changing it there affects all five
pages, which is normally what's wanted.

Blocks exposed: `{% block title %}`, `{% block head %}`, `{% block content %}`, `{% block scripts %}`.

Page-specific JavaScript goes in that page's `{% block scripts %}`. Precedent: the "See how it
works" video modal is entirely inside `landing.html`. `static/js/main.js` is loaded on every page
but is currently just a comment — it's the curriculum's intended home for shared JS.

### CSS: one stylesheet, token-driven

**There is a single `static/css/style.css`.** There is no `landing.css` or per-page stylesheet;
requests naming one are mistaken. The file is organised in commented banner sections
(Variables, Reset, Navbar, Hero, Buttons, Features, CTA, Auth pages, Legal pages, Video modal,
Footer, Responsive) — add new work as a new banner section rather than scattering rules.

All colour/font/radius values come from `:root` custom properties (`--ink*`, `--paper*`,
`--accent*`, `--font-display`, `--font-body`, `--radius-*`). Use them instead of raw hex.

Two deliberate exceptions:
- `.hero` declares its own scoped `--hero-*` variables, because the hero mockup uses a lighter
  green than the site's dark `--accent`.
- `.hero-btn` exists separately from `.btn-primary`/`.btn-ghost` so restyling the hero's buttons
  can't affect the CTA section, which still uses `.btn-primary`.

### Typography is intentionally split

`base.html` loads DM Serif Display + DM Sans. The hero (`.hero-title`, `.stat-value`) uses
**DM Sans 700**; the rest of the site — `.feature-title`, `.cta-title`, `.auth-title`,
`.legal-title`, `.modal-title` — uses **DM Serif Display**. This came from a hero-only mockup
redesign and is a known inconsistency, not an accident. The `700` weight is in the Google Fonts
URL specifically for the hero.

### Sessions: `current_user` is injected, not passed

Only `user_id` goes into the signed session cookie. A context processor in `app.py`
(`inject_current_user`) resolves it to the `users` row and injects `current_user` into **every**
template, so views never pass it explicitly — `base.html`'s navbar reads it directly to swap
Sign in / Get started for the user's name and Log out. It is `None` when logged out, and clears a
stale session if the row has since been deleted.

Guard a logged-in route with `@login_required` placed **below** `@app.route` (the route decorator
must stay outermost). It only checks for the session key; it does not load the user.

### Legal pages share a class system

`terms.html` and `privacy.html` are structurally identical and both use the `legal-*` classes
(`legal-badge`, `legal-title` + `em`, `legal-card`, `legal-heading` + `legal-num`, `legal-list`,
`legal-footnote`). A new legal page needs no new CSS — copy the structure.

Their content is generic placeholder text, not reviewed legal copy. Note privacy section 4 names
Google Fonts as the only third party; the video modal uses `youtube-nocookie.com`. Changing
either means that section needs updating.

## Known gaps

- Auth is implemented through Step 3: `/register` creates the account, `/login` starts the session,
  `/logout` clears it. `/profile` is guarded but still returns its placeholder string — Step 4's
  work. The expense routes (Steps 7–9) are still placeholders and are **not** guarded yet.
- The privacy policy describes hashed passwords, profile editing, and data export. None exist yet;
  it's a statement of intent.
- `templates/landing.html` — the "See how it works" modal trigger is `<a href="#">`. The other
  hero button links to `/register`.

## Conventions

- Work commits directly to `main`; `main` is the default branch (not `master`).
- `file.md` and `text.txt` are gitignored — they're a conversation export and a scratch notes
  file, not project sources.
