etl() {
    python extract.py data/raw/$1 data/extracted/$2.json
    python parse.py data/extracted/$2.json data/parsed/$2.json
    python standardize.py data/parsed/$2.json data/standardized/$2.json
}

for i in data/raw/*
do
    base=$(basename $i)
    filename="${base%.*}"
    etl $base $filename &
done
wait
python ingest.py data/standardized/*.json expenses expenses.db
