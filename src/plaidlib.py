import os
from datetime import datetime

import plaid
from plaid.api import plaid_api
from plaid.model.country_code import CountryCode
from plaid.model.institutions_get_by_id_request import InstitutionsGetByIdRequest
from plaid.model.item_get_request import ItemGetRequest
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions

configuration = plaid.Configuration(
    host=plaid.Environment.Development,
    api_key={
        "clientId": os.environ["PLAID_CLIENT_ID"],
        "secret": os.environ["PLAID_SECRET"],
    },
)
api_client = plaid.ApiClient(configuration)
client = plaid_api.PlaidApi(api_client)


def get_item(access_token):
    return client.item_get(
        ItemGetRequest(
            access_token=access_token,
        )
    )["item"]


def get_institution(access_token, institution_id, country_codes=[CountryCode("US")]):
    return client.institutions_get_by_id(
        InstitutionsGetByIdRequest(
            institution_id=institution_id,
            country_codes=country_codes,
        )
    )["institution"]


def get_transactions(access_token, start_date, end_date):
    options = TransactionsGetRequestOptions()
    options.count = 500
    options.offset = 0

    while True:
        response = client.transactions_get(
            TransactionsGetRequest(
                access_token=access_token,
                start_date=datetime.strptime(start_date, "%Y-%m-%d").date(),
                end_date=datetime.strptime(end_date, "%Y-%m-%d").date(),
                options=options,
            )
        )
        for tx in response["transactions"]:
            yield tx
        options.offset += len(response["transactions"])
        if len(response["transactions"]) == 0:
            break
