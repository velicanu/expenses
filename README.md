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

Spin up the main UI via:

```bash
EXPENSES_USER=dragos streamlit run src/main.py
```

Then open http://localhost:8501 on your browser. There is sample data to play with
in the `data/sample/` directory that can be used to test the code / UI.

## Demo

The following 5 minute demo shows how to get started and use the app.

[![Expense App Demo](https://img.youtube.com/vi/R7jQGC20cQg/0.jpg)](https://www.youtube.com/watch?v=R7jQGC20cQg)

## Usage

The first step to using this tool is obtaining the credit card transaction data.
You can usually download a full year's worth of data at a time from each account.

Once you obtain your data you can start using the UI.

1. `Browse` and `Submit` buttons let you add the raw the data into the app's internal folder. Currently only `csv` files are supported.
2. `Run Pipeline` button runs the data processing workflow that puts the data into a database.
3. The visualization section of the UI should automatically pick up the updated data after the pipeline runs.

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
  - This is the sqlite database where the final data is stored in. The UI reads all its data from this database.

## Development

### Run checks

```bash
make checks
# or
ruff format --check .
ruff check .
pytest
```

### Dependencies

Dependencies are declared in `pyproject.toml` and compiled into `requirements.txt`. This separation keeps dependency declarations simple while ensuring reproducible installs with pinned versions.

```bash
make compile
# or
uv pip compile pyproject.toml > requirements.txt
```

### Removing old plaid items:

```
curl -X POST https://production.plaid.com/item/remove   -H 'Content-Type: application/json'   -d '{
    "client_id": "${PLAID_CLIENT_ID}",
    "secret": "${PLAID_SECRET}",
    "access_token": String
  }'
```
