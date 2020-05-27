SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

etl() {
    python $SCRIPT_DIR/src/extract.py $SCRIPT_DIR/data/raw/$1 $SCRIPT_DIR/data/extracted/$2.json
    python $SCRIPT_DIR/src/parse.py $SCRIPT_DIR/data/extracted/$2.json $SCRIPT_DIR/data/parsed/$2.json
    python $SCRIPT_DIR/src/standardize.py $SCRIPT_DIR/data/parsed/$2.json $SCRIPT_DIR/data/standardized/$2.json
}


mkdir -p $SCRIPT_DIR/data/extracted $SCRIPT_DIR/data/parsed $SCRIPT_DIR/data/standardized
for i in $SCRIPT_DIR/data/raw/*
do
    base=$(basename $i)  # ex. amex.xlsx
    filename="${base%.*}"  # ex. amex
    etl $base $filename &
done
wait
python $SCRIPT_DIR/src/ingest.py $SCRIPT_DIR/data/standardized/*.json expenses $SCRIPT_DIR/expenses.db
