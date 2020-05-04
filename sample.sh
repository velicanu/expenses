echo "Copying data from sample folder into raw folder:"
echo cp data/sample/* data/raw/
echo
cp data/sample/* data/raw/

echo "Running the pipeline:"
echo ./run.sh
echo
./run.sh

echo
echo "Expenses are now in expenses.db"
echo "Try:"
echo "sqlite3 expenses.db"
echo "sqlite> SELECT * FROM expenses;"
