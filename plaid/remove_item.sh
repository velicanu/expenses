#!/bin/bash

# Check if access token parameter is provided
if [[ -z "$1" ]]; then
    echo "Usage: $0 <access_token>"
    echo "Example: $0 access-production-..."
    exit 1
fi

ACCESS_TOKEN="$1"

# Check if required environment variables are set
if [[ -z "${PLAID_CLIENT_ID}" || -z "${PLAID_SECRET}" ]]; then
    echo "Error: PLAID_CLIENT_ID and PLAID_SECRET environment variables must be set"
    exit 1
fi

# Remove Plaid item
curl -X POST https://production.plaid.com/item/remove \
  -H 'Content-Type: application/json' \
  -d '{
    "client_id": "'"${PLAID_CLIENT_ID}"'",
    "secret": "'"${PLAID_SECRET}"'",
    "access_token": "'"${ACCESS_TOKEN}"'"
  }'
