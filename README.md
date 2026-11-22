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

The first step to using this tool is obtaining the credit card transaction data.
You can usually download a full year's worth of data at a time from each account.

1. **Data** tab: upload the CSVs. Files that match a known card layout are saved and the pipeline runs.
2. **Dashboard**: spending by category and over time, with the shared filter bar (dates, categories, source,
   and a description box: `a+b` is or, `a^b` is and, `!a` is not, `*` is a wildcard).
3. **Transactions**: edit a category, amount, description or date inline, add a transaction, or delete one.
   Edits live in `changes.db`, so re-running the pipeline never loses them. Delete hides a row (amount 0).
4. **Rules**: map descriptions or card categories to your own categories, then *Save and apply*.

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
