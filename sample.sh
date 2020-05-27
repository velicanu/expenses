SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

echo "Copying data from sample folder into raw folder:"
echo cp $SCRIPT_DIR/data/sample/* $SCRIPT_DIR/data/raw/
echo
mkdir -p $SCRIPT_DIR/data/raw
cp $SCRIPT_DIR/data/sample/* $SCRIPT_DIR/data/raw/

echo "Running the pipeline:"
echo $SCRIPT_DIR/run.sh
echo
$SCRIPT_DIR/run.sh

echo
echo "Expenses are now in expenses.db"
echo "Try:"
echo "sqlite3 expenses.db"
echo "sqlite> SELECT * FROM expenses;"
