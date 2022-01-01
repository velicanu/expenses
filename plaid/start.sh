[[ ! -d "./quickstart" ]] && git clone https://github.com/plaid/quickstart.git && cd quickstart && git checkout 828f8c83d0dab09b22e8faae2213f3c73011e2d5 && cd -

[[ -z "${PLAID_SECRET}" || -z "${PLAID_CLIENT_ID}" ]] && echo Plaid env variables PLAID_SECRET and PLAID_CLIENT_ID need to be set, exiting. && exit 1

docker ps > /dev/null 2>&1
[[ $? -ne 0 ]] && echo Docker not running, exiting. && exit 1

cp server.py quickstart/python/
cp index.tsx quickstart/frontend/src/Components/Headers/
cd quickstart
make up language=python
cd -
