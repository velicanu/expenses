# Expenses

This repository gathers data from different credit cards and bank  transactions exports
and standardizes it in order to figure out incomnig and outgoing cash flows.

## Installation

Clone/fork this repository from it do the following:

```bash
git clone https://github.com/velicanu/expenses.git
cd expenses/
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Getting started

Spin up the main UI via:

```bash
SKIP_AUTH=true streamlit run src/Home.py
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

The linting checks and tests are the following:
```
ruff check .
ruff format --check .
pytest
```

### Requirements

Requirements for this project are specified in two files, a `requirements.in` file and a
`requirements.txt` file. The requirements.in file is where we manually insert the
dependencies this project needs and the requirements.txt is auto-generated from the .in
file using `uv pip compile`. The workflow for adding or updating some dependencies looks
like the following:

```bash
# one time install uv
pip install uv

# update something in requirements.in
uv pip compile requirements.in > requirements.txt

# the requirements.txt file has been auto-generated with pinned dependencies
uv pip install -r requirements.txt
```

The benefit of this approach is that we can ensure all environments (dev / ci / etc)
have the same exact same versions of each dependency installed, while making it easy to
add and update top level requirements.
