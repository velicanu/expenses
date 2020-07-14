# Expenses

This repository gathers data from different credit card transactions exports and
standardizes it in order to figure out where money is being spent.

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
python src/app.py
```

Then open http://localhost:5000 on your browser. There is sample data to play with
in the `data/sample/` directory that can be used to test the code / UI.

## Usage

The first step to using this tool is obtaining the credit card transaction data.
You can usually download a full year's worth of data at a time from each account.

Once you obtain your data you can start using the UI.

1. `Browse` and `Submit` buttons let you add the raw the data into the app's internal folder. Currently only `csv` files are supported.
2. `Run Pipeline` button runs the data processing workflow that puts the data into a database.
3. The visualization section of the UI should automatically pick up the updated data after the pipeline runs.


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

`black` + `isort` for python code. `prettier` for html/js

### Tests

```bash
nosetests -v .
```
