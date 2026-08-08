# Spec: Profile Date Filter

## Overview

Give `/profile` a date range filter. Step 5 wired the page to the database, but it reads a user's
*entire* history every time — "Total spent" is lifetime spend, "Where it goes" is a lifetime
breakdown, and there is no way to ask the only question people actually ask an expense tracker:
*what did I spend this month?* This step adds a small filter bar above the stats with four presets
(This month, Last 30 days, This year, All time) plus a custom from/to range, driven entirely by
query-string parameters on the existing `GET /profile`. Every one of Step 5's three queries gains
the same date bounds, so the stats, the transaction table and the category bars always describe the
same window.

It is deliberately a *read-side* feature and sits before the expense CRUD in Steps 7–9: filtering
teaches building a `WHERE` clause from untrusted user input — a whitelist for the preset, `?`
placeholders for the dates, and a fallback for anything malformed — without any of the write-path
risk. Because the filter lives in the URL, a filtered view is shareable and bookmarkable, and the
back button works; no session state and no JavaScript are involved.

## Depends on

- **Step 1 — Database Setup** (complete): `get_db()` and `expenses.date`, stored as ISO
  `YYYY-MM-DD` text (`database/db.py:51-61`). String comparison on that format is chronological,
  which is what makes `date >= ? AND date <= ?` correct without any SQL date parsing.
- **Step 3 — Login and Logout** (complete): `session["user_id"]` and `login_required`. The filter
  narrows the rows a user sees; it never widens them past their own `user_id`.
- **Step 4 — Profile Design** (complete): the `profile-*` / `cat-*` class system the new filter bar
  extends.
- **Step 5 — Profile Backend Route** (complete): the three queries in `profile()`
  (`app.py:191-224`) that this step adds bounds to, and the `.profile-empty` empty state
  (`static/css/style.css:1039`) it reuses.

The expense placeholder routes for Steps 7–9 stay untouched and unguarded — that is their own
steps' work.

## Routes

**No new routes.**

- `GET /profile` — render the profile page, optionally narrowed to a date range read from the query
  string — logged-in
  *(exists; `@app.route("/profile")`, `@login_required` and the endpoint name `profile` are all
  unchanged — only the view body grows)*

Query parameters, all optional:

| Param | Values | Meaning |
| --- | --- | --- |
| `range` | `month`, `30d`, `year`, `all`, `custom` | which preset; anything else falls back to `all` |
| `from` | `YYYY-MM-DD` | start date, inclusive — read only when `range=custom` |
| `to` | `YYYY-MM-DD` | end date, inclusive — read only when `range=custom` |

`/profile` with no parameters must behave exactly as it does today (all time).

## Database changes

**No database changes.** `expenses.date` already exists and already holds the ISO text this step
compares against. No new column, no migration, no index — at teaching scale a scan is fine, and an
index on `expenses(user_id, date)` is a legitimate later optimisation that is out of scope here.

## Templates

- **Create:** none.
- **Modify:** `templates/profile.html`
  1. **Filter bar.** A new `<form method="get" action="{{ url_for('profile') }}">` block between
     the `.profile-header` and `.profile-stats`. It holds the four preset links/buttons and the two
     `<input type="date" name="from">` / `name="to"` fields plus an Apply button. `method="get"` is
     required — the filter must end up in the URL, not in a POST body.
  2. **Active state.** The preset matching `active_range` gets an `is-active` class (and the custom
     inputs are pre-filled with `date_from` / `date_to`) so a reloaded or shared URL visibly shows
     which range is applied.
  3. **Range caption.** A short line under the stats reading e.g. *"1 – 31 August 2026"* or
     *"All time"*, from a `range_label` passed by the view. Without it "Total spent ₹250" is
     ambiguous.
  4. **Filtered empty states.** The existing `{% for %}…{% else %}` blocks say *"No expenses yet."*
     and *"Nothing to break down yet."* — both wrong when the account has expenses but none in the
     chosen window. Switch the copy on whether a filter is active (e.g. *"No expenses in this
     range."*), and in that case include a link back to `/profile` to clear it.
  5. **Validation message.** When the view reports a bad custom range, render the existing
     error-message pattern above the filter bar rather than failing silently.

`profile.html` keeps extending `base.html`. No new template file is needed and no page-specific
`{% block scripts %}` is added — this feature is plain HTML form submission, not JavaScript.

## Files to change

- **`app.py`**
  - Add a module-level helper, `resolve_range(args)`, above `profile()`, that turns
    `request.args` into `(start, end, label, active, error)` where `start`/`end` are ISO strings or
    `None`. Keeping it out of the view keeps `profile()` readable and makes the logic unit-testable
    without a request context.
    - Whitelist the preset: `range` not in `{"month", "30d", "year", "all", "custom"}` → treat as
      `all`. Never branch on an unchecked string.
    - `month` → first of the current month through today. `30d` → today minus 29 days through
      today (29, so the window is 30 days inclusive). `year` → 1 January of the current year
      through today. `all` → `(None, None)`.
    - `custom` → parse `from` and `to` with `datetime.strptime(value, "%Y-%m-%d")`. Either may be
      omitted, giving an open-ended bound. A value that will not parse, or `from` later than `to`,
      is an error: return the `all` window plus an error message, so the page still renders.
    - Build `label` here too, using the existing `fmt_date` formatting style — the template should
      not be doing date arithmetic.
  - In `profile()`, call the helper once and apply the **same** bounds to all three queries. Build
    the clause and parameter list once and reuse it, so the three queries cannot drift apart:

    ```python
    where = "WHERE user_id = ?"
    params = [user_id]
    if start:
        where += " AND date >= ?"
        params.append(start)
    if end:
        where += " AND date <= ?"
        params.append(end)
    ```

    Interpolating `where` into the SQL string is safe **only** because it is built from literals in
    this function; every user-supplied value goes in through `params` as a `?`.
  - Pass `range_label`, `active_range`, `date_from`, `date_to` and `range_error` to
    `render_template` alongside the existing `summary`, `transactions`, `categories`.
  - Everything Step 5 established stays: one connection, closed in `finally`; `top_category`
    derived from the first category row; `percent` relative to the largest category — now the
    largest *within the filtered window*, so bars still fill their track.

- **`templates/profile.html`** — the five changes described above.

- **`static/css/style.css`** — a new commented banner section (e.g. `/* === Profile filter === */`)
  at the end of the file for `.profile-filter`, `.profile-filter-option`, `.profile-filter-option.is-active`,
  `.profile-filter-dates`, `.profile-range-label`. Do not edit the existing Profile section, per
  CLAUDE.md.

- **`CLAUDE.md`** — update the *Profile page* section to record that `/profile` accepts a date range
  from the query string and that all three queries share one set of bounds.

## Files to create

**No new files.**

## New dependencies

**No new dependencies.** `datetime` (already imported in `app.py:4`) covers every date calculation
here. Do not add `dateutil`, `arrow`, or a date-picker library — `<input type="date">` is native.

## Rules for implementation

- **No SQLAlchemy or ORMs** — raw `sqlite3` through `get_db()` only.
- **Parameterised queries only.** Every date bound is a `?` placeholder. An f-string or `%`-format
  that puts `request.args["from"]` into SQL text is the one unacceptable outcome of this step,
  even though the value "looks like a date".
- **Whitelist the preset before branching on it.** `range` is attacker-controlled text; compare it
  against a fixed set and fall back to `all`.
- **Passwords hashed with werkzeug** — unchanged; this step must not touch `register()`, `login()`
  or `password_hash`.
- **Use CSS variables** — the new filter rules resolve `--ink*`, `--paper*`, `--accent*`,
  `--radius-*`. Never hardcode a hex value. Do not reuse the hero's `.stat-card` /
  `.preview-bars` / `.preview-fill` classes; they resolve `--hero-*` scoped to `.hero`.
- **All templates extend `base.html`** — `profile.html` already does; keep it that way.
- **Every query stays scoped by `user_id`.** The date clause is *added to* `WHERE user_id = ?`,
  never substituted for it.
- **All three queries share one window.** If the table shows August but the bars show all time, the
  page is lying. Build the clause once.
- **A bad range must not 500.** Unparseable dates, `from` after `to`, `range=';DROP TABLE'`,
  `from=9999-99-99` — all render the page with a message, not a traceback.
- **Reuse the existing template filters.** `fmt_date` and `rupees` (`app.py:69-86`) still do all
  date and currency formatting in the markup. The range *label* is built in Python because it
  joins two dates into one phrase.
- **Do not change the existing template data contract.** `summary.total_spent`,
  `summary.transaction_count`, `summary.top_category`, `transactions[].date/description/category/
  amount`, `categories[].name/total/percent` keep their names and shapes.
- **No JavaScript.** A GET form and links only, so the filter works with the back button and can be
  shared as a URL. `static/js/main.js` stays as it is.
- **Leave the Step 7–9 placeholders alone**, including their missing `@login_required`.

### Defaults chosen here

Recorded so they are decisions rather than accidents:

- **Default is All time**, not This month — a bare `/profile` must render exactly what it renders
  today, so this step cannot break Step 5's behaviour or its tests.
- **Bounds are inclusive on both ends.** `from=2026-08-01&to=2026-08-31` includes both days.
- **`30d` means today and the 29 days before it**, i.e. 30 days counting today, not 31.
- **Ranges end at today, not at the end of the period.** "This year" is 1 Jan → today; future-dated
  expenses are therefore excluded from presets. Custom ranges may reach into the future.
- **The transaction table keeps `LIMIT 10`.** The filter narrows the window, it does not turn the
  card into a full history — pagination is its own feature.
- **`percent` stays relative to the largest category in the window**, so the top bar always fills
  its track regardless of range.

## Definition of done

Run the app with `.\venv\Scripts\python.exe app.py` and check each item at
`http://127.0.0.1:5001`, signed in as `demo@spendly.com` / `demo123`:

1. `/profile` with no query string renders exactly as it did before this step — same total, same
   transaction count, same category bars — and the caption reads "All time".
2. The filter bar appears above the stats with four presets and two date inputs, and its colours
   come from CSS variables — `grep -nE "#[0-9a-fA-F]{3,6}" static/css/style.css` shows no new hex
   outside `:root`.
3. Clicking **This month** changes the URL to `/profile?range=month`, the caption names the month,
   and the "This month" preset renders in its active state after the reload.
4. Insert an expense dated well outside the current month, e.g.
   `.\venv\Scripts\python.exe -c "from database.db import get_db; c=get_db(); c.execute('INSERT INTO expenses (user_id, amount, category, date, description) VALUES (1, 500, \"Food\", \"2020-01-15\", \"Old lunch\")'); c.commit()"`.
   It appears under **All time** and disappears under **This month** — and All time's total is
   exactly ₹500 higher than before the insert.
5. Stats, table and bars agree: under any preset, the "Transactions" stat equals the number of rows
   the same filter would return (verify with `LIMIT 10` in mind — use a range with fewer than 10
   rows), and no category bar shows spend from a date outside the caption's window.
6. `/profile?range=custom&from=2026-08-01&to=2026-08-03` shows only expenses in those three days,
   inclusive of both endpoints, and the two date inputs come back pre-filled with those values.
7. `/profile?range=custom&from=2026-08-31&to=2026-08-01` (reversed) renders the page with a
   validation message and falls back to all time — HTTP 200, no traceback.
8. `/profile?range=custom&from=not-a-date`, `/profile?range=9999`, and
   `/profile?range=custom&from=2026-13-45` each return 200, not 500. Verify with the test client:
   ```python
   import app
   c = app.app.test_client()
   with c.session_transaction() as s: s["user_id"] = 1
   for q in ["", "?range=month", "?range=9999", "?range=custom&from=not-a-date",
             "?range=custom&from=2026-08-31&to=2026-08-01"]:
       print(q, c.get("/profile" + q).status_code)
   ```
9. `grep -nE "f\"|format\(|%s" app.py` shows no user value interpolated into any SQL string; every
   date reaches SQLite through a `?` placeholder.
10. A second account (e.g. `pooja.yadav874@gmail.com`) filtered to the same range shows only its own
    expenses — no figure from Demo User's page appears. Every query still contains
    `WHERE user_id = ?`.
11. An account with **zero** expenses in the selected range shows the filtered empty state
    ("No expenses in this range.") with a link that clears the filter, and ₹0 / 0 / — in the stats.
    An account with no expenses at all still shows "No expenses yet.".
12. Visiting `/profile?range=month` while logged out redirects to `/login` — `@login_required`
    survived, and the query string does not bypass it.
13. `.\venv\Scripts\python.exe -c "import app; print(app.app.url_map)"` lists `/profile` once, as
    endpoint `profile` — the route table is unchanged.
