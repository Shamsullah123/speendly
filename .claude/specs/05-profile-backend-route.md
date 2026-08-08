# Spec: Profile Backend Route

## Overview

Connect `/profile` to the database. Step 4 built the whole profile UI against
`DEMO_PROFILE_DATA` — a hardcoded dict in `app.py:95-122` that every signed-in user sees
identically, so Demo User, Pooja and a brand-new account all show the same ₹8,143.52. This step
deletes that dict and replaces it with three parameterised queries against the `expenses` table,
scoped to `session["user_id"]`, so the summary stats, the transaction table and the category bars
finally describe the person looking at them. It is the first feature to *read* expense rows rather
than users, and it is the step that makes the expense CRUD in Steps 7–9 worth building — without it
an added expense would never appear anywhere in the UI.

The template's contract does not change. `DEMO_PROFILE_DATA` was deliberately shaped like query
output (ISO date strings, float amounts, the seven fixed categories), so `profile.html` keeps
reading `summary.total_spent`, `t.category`, `c.percent` exactly as it does now. The only template
work is the empty state, which Step 4 never needed and which is now unavoidable: two of the four
accounts in the current database have zero expenses.

## Depends on

- **Step 1 — Database Setup** (complete): `get_db()` and the `expenses` table with its
  `user_id`, `amount`, `category`, `date`, `description` columns (`database/db.py:49-62`).
- **Step 2 — Registration** (complete): supplies the accounts that own the rows.
- **Step 3 — Login and Logout** (complete): supplies `session["user_id"]`, the `login_required`
  decorator and the `inject_current_user` context processor. This step reads the session to scope
  its queries; it does not touch auth.
- **Step 4 — Profile Design** (complete): supplies `templates/profile.html` and the `profile-*` /
  `cat-*` class system this step feeds with real numbers.

Nothing else. The expense placeholder routes for Steps 7–9 stay untouched and unguarded — that is
their own steps' work and must not be picked up here.

## Routes

**No new routes.**

- `GET /profile` — render the profile page from live database rows — logged-in
  *(exists; `@app.route` + `@login_required` + view name all unchanged — only the body changes)*

## Database changes

**No database changes.** The `expenses` table already holds every column this step reads
(`database/db.py:51-61`):

| Needed for | Column |
| --- | --- |
| scoping every query to the signed-in user | `user_id` |
| totals, category sums, table amounts | `amount` |
| category badges and breakdown bars | `category` |
| table dates and ordering | `date` |
| table description cells | `description` |

`date` is stored as an ISO `YYYY-MM-DD` string, so plain `ORDER BY date DESC` sorts
chronologically — no date parsing in SQL is required.

No index is added. With a teaching-scale dataset a sequential scan is fine; an index on
`expenses(user_id)` is a legitimate later optimisation but is out of scope here.

## Templates

- **Create:** none.
- **Modify:** `templates/profile.html` — three empty-state changes only. The existing markup,
  classes and filter calls stay exactly as they are.
  1. **Top-category fallback.** `summary.top_category` is `None` for a user with no expenses, and
     Jinja renders that as the literal text `None`. Guard it so it shows an em dash instead.
  2. **Empty transaction table.** Wrap the `{% for t in transactions %}` loop so that when the list
     is empty the table body shows a single full-width cell reading something like
     *"No expenses yet."* rather than a headed table with nothing under it.
  3. **Empty category breakdown.** Same treatment for the `{% for c in categories %}` loop inside
     the "Where it goes" card.

## Files to change

- **`app.py`**
  - Delete the `DEMO_PROFILE_DATA` constant and the `# Demo data — Step 5 replaces this`
    banner comment above it (lines 89-122).
  - Rewrite the `profile()` view body to open one connection, run the three queries below, close
    the connection in a `finally`, and pass `summary`, `transactions` and `categories` to
    `render_template`. Keep `@app.route("/profile")` and `@login_required` as they are.
  - Read the user id from `session["user_id"]`. Do **not** call `current_user()` for it — that
    would be a third connection for an id the session already holds.

  **Query 1 — summary totals** (one row, always):
  ```sql
  SELECT COUNT(*) AS transaction_count,
         COALESCE(SUM(amount), 0) AS total_spent
  FROM expenses
  WHERE user_id = ?
  ```
  `COALESCE` matters: bare `SUM` over zero rows returns `NULL`, which would reach the `rupees`
  filter and render as an empty cell.

  **Query 2 — recent transactions** (feeds the table):
  ```sql
  SELECT date, description, category, amount
  FROM expenses
  WHERE user_id = ?
  ORDER BY date DESC, id DESC
  LIMIT 10
  ```
  `id DESC` is the tiebreaker so several expenses on the same day come back newest-first and in a
  stable order between requests.

  **Query 3 — category totals** (feeds the bars *and* the top-category stat):
  ```sql
  SELECT category, SUM(amount) AS total
  FROM expenses
  WHERE user_id = ?
  GROUP BY category
  ORDER BY total DESC
  ```

  **Derivations in Python, not SQL:**
  - `top_category` is the `category` of query 3's first row, or `None` when there are no rows. Do
    not run a fourth `ORDER BY ... LIMIT 1` query for it — deriving it here also guarantees the
    stat can never disagree with the bar chart.
  - `percent` for each category is its total as a percentage **of the largest category's total**,
    not of overall spend. This reproduces Step 4's visual behaviour exactly: in
    `DEMO_PROFILE_DATA` the top category Shopping sits at `100`, Bills at `72` (2240.75/3120),
    Health at `27`, so the widest bar always fills its track. Because query 3 is sorted
    descending, the divisor is the first row's total. Round to an integer.
  - Query 3's rows must be converted to plain dicts (`{"name": ..., "total": ..., "percent": ...}`)
    because `sqlite3.Row` is immutable and `percent` is added after the fetch. Note the key is
    `name`, which is what `profile.html:65` and `:67` already read.
  - Query 1's and query 2's rows can stay as `sqlite3.Row` objects. Jinja's `summary.total_spent`
    and `t.description` work on them: attribute lookup fails, and Jinja falls back to
    `["subscript"]` access.

- **`templates/profile.html`** — the three empty-state edits described above.

- **`static/css/style.css`** — one new rule for the empty-state text (a muted, centred
  `.profile-empty`). Add it as a **new commented banner section** at the end rather than editing
  the existing Profile section, per the convention in CLAUDE.md.

- **`CLAUDE.md`** — update two places that this step makes untrue:
  - The *Profile page* section's claim that the figures "come from `DEMO_PROFILE_DATA` in `app.py`,
    **not** the database".
  - The *Known gaps* bullet stating `/profile`'s figures are hardcoded and "Step 5 replaces
    `DEMO_PROFILE_DATA` with queries".

## Files to create

**No new files.**

## New dependencies

**No new dependencies.** `flask` and `werkzeug` already cover this; nothing here needs a new
package.

## Rules for implementation

- **No SQLAlchemy or ORMs** — raw `sqlite3` through `get_db()` only.
- **Parameterised queries only** — never string-format or f-string a value into SQL. Every one of
  the three queries takes `user_id` as a `?` placeholder.
- **Passwords hashed with werkzeug** — unchanged; this step must not touch `register()`, `login()`
  or `password_hash` in any way.
- **Use CSS variables** — the new `.profile-empty` rule must resolve `--ink*` / `--paper*` tokens.
  Never hardcode a hex value.
- **All templates extend `base.html`** — `profile.html` already does; keep it that way.
- **Every query is scoped by `user_id`.** A query over `expenses` without `WHERE user_id = ?` is a
  data leak between accounts, not a style problem. This is the single most important rule in this
  step.
- **One connection, closed in `try`/`finally`.** Follow the existing pattern in `current_user()`
  (`app.py:45-51`) and `login()` (`app.py:190-196`): open with `get_db()`, fetch, close in
  `finally`. Run all three queries on that one connection — do not open one per query. No `with
  conn:` transaction block is needed; these are reads.
- **Reuse the existing template filters.** `fmt_date` and `rupees` (`app.py:69-86`) already do the
  date and currency formatting. Do not format dates or prepend ₹ in Python, and do not add a new
  filter.
- **Do not change the template's data contract.** Keys stay `summary.total_spent`,
  `summary.transaction_count`, `summary.top_category`, `transactions[].date/description/category/
  amount`, `categories[].name/total/percent`. Renaming any of them means editing markup that Step 4
  signed off.
- **Do not reuse the hero's `.stat-card` / `.preview-bars` / `.preview-fill` classes**, per
  CLAUDE.md — they resolve `--hero-*` variables scoped to `.hero`.
- **Leave the Step 7–9 placeholders alone**, including their missing `@login_required`. Guarding
  them is their own steps' work.

### Defaults chosen here

Recorded so they are decisions rather than accidents:

- **Transaction table shows the 10 most recent.** `DEMO_PROFILE_DATA` showed 6, but a fixed small
  cap keeps the card a readable size; a full paginated history is its own feature.
- **The breakdown shows every category with spend, not a top 5.** `DEMO_PROFILE_DATA` listed only 5
  and silently dropped Transport (₹500). Hiding real spending on a page whose heading is "Where it
  goes" is the wrong default, so all categories present are shown — at most 7.
- **`percent` is relative to the largest category**, preserving Step 4's bar proportions, rather
  than being switched to a share-of-total reading.

## Definition of done

Run the app with `.\venv\Scripts\python.exe app.py` and check each item at
`http://127.0.0.1:5001`:

1. `grep DEMO_PROFILE_DATA app.py` returns nothing — the constant and its banner comment are gone.
2. Signing in as `demo@spendly.com` / `demo123` shows **Total spent ₹250**, **8 transactions** and
   top category **Bills** — Demo User's real seeded figures, not ₹8,143.52.
3. That account's "Where it goes" card shows **7 bars** (Bills, Shopping, Food, Health,
   Entertainment, Transport, Other), the top one filling the full track width, each bar keeping its
   `cat-*` colour.
4. Signing in as a **second** account with expenses (e.g. `pooja.yadav874@gmail.com`) shows
   *different* numbers — 6 transactions, ₹4,724.62, 4 category bars. No figure from Demo User's
   page appears on it.
5. Signing in as an account with **zero** expenses (e.g. `shamsullahkhan94@gmail.com`) shows
   **₹0**, **0** transactions, an em dash for top category — **not** the text "None" — and the
   "No expenses yet." empty state in both cards. No traceback, no 500.
6. Every amount still renders as `₹1,234` and every date as `05 Aug 2026`, confirming `rupees` and
   `fmt_date` are still doing the formatting.
7. Transactions appear newest date first; two expenses sharing a date appear in a stable order
   across a page refresh.
8. Visiting `/profile` while logged out still redirects to `/login` — `@login_required` survived
   the rewrite.
9. Inserting a new expense row directly via
   `.\venv\Scripts\python.exe -c "..."` and refreshing `/profile` shows it in the table and moves
   the totals, proving the page reads live data.
10. `.\venv\Scripts\python.exe -c "import app; print(app.app.url_map)"` lists `/profile` once, as
    endpoint `profile` — the route table is unchanged.
