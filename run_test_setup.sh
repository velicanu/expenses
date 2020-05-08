TESTDIR="$1"

mkdir -p $TESTDIR/data
cp -r src/ $TESTDIR/src/
cp -r data/sample $TESTDIR/data/
cp sample.sh run.sh $TESTDIR/
$TESTDIR/sample.sh &> /dev/null
