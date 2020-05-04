etl() {
    python src/extract.py data/raw/$1 data/extracted/$2.json
    python src/parse.py data/extracted/$2.json data/parsed/$2.json
    python src/standardize.py data/parsed/$2.json data/standardized/$2.json
}


mkdir -p data/extracted data/parsed data/standardized
for i in data/raw/*
do
    base=$(basename $i)  # ex. amex.xlsx
    filename="${base%.*}"  # ex. amex
    etl $base $filename &
done
wait
python src/ingest.py data/standardized/*.json expenses expenses.db
