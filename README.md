# Expenses

This repository gathers data from different credit card transactions exports and
standardizes it in order to figure out where money is being spent.

## Installation

Clone/fork this repository from it do the following:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Getting started

You can see the pipeline run on some sample data by running the following script:

```bash
./sample.sh
```

## Usage

Put your own exported credit card transactions in the `data/raw/` directory,
the filenames need to respect the following conventions:
- American Express files must start with `amex`
- Capital One files must start with `capital`
- Chase files must start with `chase`
- USBank (REI) files must start with `usbank`

Currently `csv` and `xlsx/xls` files are supported.

After putting your data into the raw directory, run the following script to ingest it:

```bash
./run.sh
```

### Analysis

After running the pipeline, the data will be in standardized form in a sqlite database
`expenses.db` as well in json format in the `data/standardized` directory.