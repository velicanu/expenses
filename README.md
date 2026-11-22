# Expenses

This repository gathers data from different credit cards and bank transactions exports
and standardizes it in order to figure out incomnig and outgoing cash flows.

## Installation

Clone/fork this repository from it do the following:

```bash
git clone https://github.com/velicanu/expenses.git
cd expenses/
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

## Getting started

The app is a FastAPI server (`src/server/`) plus a React web app (`web/`).

```bash
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
make dev                      # the API on http://127.0.0.1:8094, acting as user "dragos", data in ./data/dragos
cd web && npm ci && npm run dev   # the web app on http://localhost:5173, proxying /api to the API
```

Drop the CSVs from `sample-data/` into the Data tab to try it. `make web` builds the web app into
`web/dist`; the server serves it at `/` when `STATIC_DIR` points there (the Dockerfile does that).

`DEV_USER` skips the login and is for local use only. In production the login happens in front of the
app (see Deployment) and it trusts the `X-Email` header only from its reverse proxy.

## Demo

The demo video below shows the previous (Streamlit) interface; the workflow is the same.

[![Expense App Demo](https://img.youtube.com/vi/R7jQGC20cQg/0.jpg)](https://www.youtube.com/watch?v=R7jQGC20cQg)

## Usage

The page is the old Streamlit page, rebuilt: a **sidebar** with the filters, and the **charts** in the main area.

- **Sidebar form** (applies on **Submit**): date range, *Categories in*, *Categories not in*, *Description*
  (`a+b` is or, `a^b` is and, `!a` is not, `*` is a wildcard) and *Source file*. Your selections are saved with the
  data (`config.json`), so every device opens with the same filters, as the old app did.
- **Inputs**: upload CSVs (a recognised card layout is saved and the pipeline runs), *Run pipeline*,
  *Refresh data* (Plaid, for already linked accounts), delete raw files.
- **Rules**: map descriptions or card categories to your own categories (and colors), then *Apply rules*.
- **Show data**: the SQL the filters build (editable; it runs over table `expenses`) and the data, editable in place,
  with *Save Changes*, and a **+** to add a row. Edits live in `changes.db`, so re-running the pipeline never loses them.
- **Charts**: spending by category (table and pie) and spending over time with a *Time bin* slider.

Numbers and colors are identical to the old app, and keeping them that way:

- the charts are built **on the server with the same Plotly Express code** (`src/server/figures.py`) and the
  SQL box text by the same rules (`src/server/sqlview.py`), then drawn by plotly.js;
- Streamlit's browser code also themed every chart (its palette for categories with no color of their own, bold
  titles, light/dark); `web/src/streamlitTheme.ts` does the same, from templates captured from the old app in a real
  browser;
- `tests/golden/old_ui.json` was captured from the real old app (`python tests/golden/make_golden.py`), and
  `tests/test_parity.py` requires the same figures and SQL, scenario by scenario, so it stays true after
  `src/main.py` is gone.

Kept on purpose, because they are the old numbers: the end date of the range is compared as text, so rows **on** the
last day are left out; and a lone `!term` in the description box is not negated (only `a+!b` or `a^!b` are).
Different from the old app: the SQL box is read-only (SELECT only, 10 s, 50,000 rows).

### Plaid integration

See the documentation in `./plaid/README.md` for instructions on how to setup Plaid to
automatically pull transactions.

### Internal files

All intermediate data is available should you want it in the `data/` directory.
- `data/raw`
  - where the CSV's added through the UI are stored
- `data/extracted`
  - the folder contains `json` versions of the csv files, this is the first step of the pipeline
- `data/parsed`
  - this folder contains json files with keys converted into a uniform schema, second step of the pipeline
- `data/standardized`
  - this folder contains json files with standardized values for fields (eg. categories and dates), third step of the pipeline
- `data/expenses.db`
  - This is the sqlite database where the final data is stored in. It is rebuilt from `raw/` on every pipeline run
    (swapped in atomically), so it can be regenerated and does not need backing up.
- `data/changes.db`
  - Your edits and added transactions. This is the one thing the pipeline cannot rebuild: back it up.
- `data/config.json`
  - Rules, new categories and linked Plaid accounts (it contains Plaid access tokens: keep it private).

## Row ids (pk)

Every transaction has a pk, `<source_file>-<line>`, and your edits in `changes.db` are keyed by it. It stays
the same as data arrives because rows are numbered in date order with a **stable** sort, after turning a
newest-first file around (most banks list newest first), so rows appended at either end of a file always
come last. It moves only if a row appears out of date order (a backdated transaction) or a row is removed
from a raw file, which shifts every later pk in that file. An edit is a full copy of its row, so an edit
whose pk now belongs to a different row replaces that row in the view: one transaction missing, another twice.
Avoid removing rows from raw files; replace the whole file with a longer export instead.

`src/migrate_pks.py` re-keys an existing `changes.db` once after the numbering changed (it did, in this
version: the old sort was unstable). See `docs/deploy.md`.

## Deployment

`expense.velicanu.com` runs on tess from the `velicanu/server` repo (`iac/expense.tf`): a Google login on pi5,
nginx in front, and this app in Docker on tess. See `docs/deploy.md`.

## API

The server's OpenAPI description is at `/api/openapi.json` (and `/api/docs`), and `web/openapi.json` is a
checked-in copy that `web/src/api.ts` is written against.

## Development

### Run checks

```bash
make checks        # ruff format --check, ruff check, pytest
make web-checks    # typecheck, lint and test the web app
```

### Dependencies

Dependencies are declared in `pyproject.toml` and compiled into `requirements.txt`. This separation keeps dependency declarations simple while ensuring reproducible installs with pinned versions.

```bash
make compile
# or
uv pip compile pyproject.toml -o requirements.txt   # -o keeps existing pins
```

### Removing old plaid items:

```
curl -X POST https://production.plaid.com/item/remove   -H 'Content-Type: application/json'   -d '{
    "client_id": "${PLAID_CLIENT_ID}",
    "secret": "${PLAID_SECRET}",
    "access_token": String
  }'
```
