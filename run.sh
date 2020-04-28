for i in data/raw/*
do
    base=$(basename $i)
    filename="${base%.*}"
    python extract.py data/raw/$base data/extracted/$filename.json
    python parse.py data/extracted/$filename.json data/parsed/$filename.json
    python standardize.py data/parsed/$filename.json data/standardized/$filename.json
done
python ingest.py data/standardized/*.json expenses expenses.db
