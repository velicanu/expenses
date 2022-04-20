[[ ! -d "./quickstart" ]] && git clone https://github.com/plaid/quickstart.git && cd quickstart && git checkout 828f8c83d0dab09b22e8faae2213f3c73011e2d5 && cd -

[[ -z "${PLAID_SECRET}" || -z "${PLAID_CLIENT_ID}" ]] && echo Plaid env variables PLAID_SECRET and PLAID_CLIENT_ID need to be set, exiting. && exit 1

cat > quickstart/.env <<EOL
PLAID_CLIENT_ID="${PLAID_CLIENT_ID}"
PLAID_SECRET="${PLAID_SECRET}"
PLAID_ENV=development
PLAID_PRODUCTS=transactions
PLAID_COUNTRY_CODES=US
PLAID_REDIRECT_URI=
EOL

docker ps > /dev/null 2>&1
[[ $? -ne 0 ]] && echo Docker not running, exiting. && exit 1

# patch server
cd quickstart ; git checkout . ; cd - ; cp requirements.txt quickstart/python
cat quickstart/python/server.py | sed '/api\/info/,+10 d' > tmp.py
cat server.py >> tmp.py
mv tmp.py quickstart/python/server.py

# # patch frontend
# head -n31 quickstart/frontend/src/Components/Headers/index.tsx | sed 's/Plaid Quickstart/Link Account/' > tmp.tsx
# cat >> tmp.tsx <<EOL
#             Click the Launch Link button and log into your account.
#             After logging in you can close this tab and click the
#             Get Token button in the expense app.
# EOL
# tail -n82 quickstart/frontend/src/Components/Headers/index.tsx >> tmp.tsx
# mv tmp.tsx quickstart/frontend/src/Components/Headers/index.tsx

cd quickstart
make up language=python
cd -
