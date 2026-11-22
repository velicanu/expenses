"""Linking a bank through Plaid Link, and reconnecting one whose login expired.

The browser runs Plaid Link; this side makes the link token, trades the public token Link hands back for the
access token, and keeps that token on the server. Access tokens are never returned by any route.

- new link: products=transactions, and `days_requested` 730. Plaid's default history for a new link is 90 days;
  the two years it allows is what lets a new link fill a gap.
- update mode (reconnect): the same call with the stored access token and no products. Plaid re-asks only for
  the bank login; the access token and the item stay the same, so nothing is relinked.
- OAuth banks (Capital One, Wealthfront, Chase ...): the browser leaves for the bank and returns to
  redirect_uri, which must be registered in the Plaid dashboard. The page resumes Link there.
"""

import json
import re
from datetime import date

ALIAS_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
# Plaid error codes that mean "the person has to log in to the bank again" (update mode fixes them)
RECONNECT_CODES = {
    "ITEM_LOGIN_REQUIRED",
    "PENDING_EXPIRATION",
    "PENDING_DISCONNECT",
    "USER_PERMISSION_REVOKED",
}
CLIENT_NAME = "Expenses"


class PlaidError(Exception):
    """A Plaid API error: its code and message (never the request, which carries keys and tokens)."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code
        self.message = message


def api_error(exc: Exception) -> PlaidError:
    """Turns a plaid ApiException (or anything else) into a PlaidError without leaking the request."""
    try:
        body = json.loads(getattr(exc, "body", "") or "{}")
        return PlaidError(
            body.get("error_code") or "PLAID_ERROR",
            (body.get("error_message") or "")[:200],
        )
    except (ValueError, TypeError):
        return PlaidError(type(exc).__name__)


def create_link_token(
    client, user: str, redirect_uri: str | None, access_token: str | None = None
) -> str:
    from plaid.model.country_code import CountryCode
    from plaid.model.link_token_create_request import LinkTokenCreateRequest
    from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
    from plaid.model.link_token_transactions import LinkTokenTransactions
    from plaid.model.products import Products

    fields = {
        "client_name": CLIENT_NAME,
        "language": "en",
        "country_codes": [CountryCode("US")],
        "user": LinkTokenCreateRequestUser(client_user_id=user),
    }
    if redirect_uri:
        fields["redirect_uri"] = redirect_uri
    if access_token:  # update mode: no products, the item already has them
        fields["access_token"] = access_token
    else:
        fields["products"] = [Products("transactions")]
        fields["transactions"] = LinkTokenTransactions(days_requested=730)
    try:
        return client.link_token_create(LinkTokenCreateRequest(**fields))["link_token"]
    except Exception as e:
        raise api_error(e) from None


def exchange_public_token(client, public_token: str) -> str:
    from plaid.model.item_public_token_exchange_request import (
        ItemPublicTokenExchangeRequest,
    )

    try:
        return client.item_public_token_exchange(
            ItemPublicTokenExchangeRequest(public_token=public_token)
        )["access_token"]
    except Exception as e:
        raise api_error(e) from None


def institution_name(client, access_token: str) -> str | None:
    from plaid.model.country_code import CountryCode
    from plaid.model.institutions_get_by_id_request import InstitutionsGetByIdRequest
    from plaid.model.item_get_request import ItemGetRequest

    try:
        institution_id = client.item_get(ItemGetRequest(access_token=access_token))[
            "item"
        ]["institution_id"]
        return client.institutions_get_by_id(
            InstitutionsGetByIdRequest(
                institution_id=institution_id, country_codes=[CountryCode("US")]
            )
        )["institution"]["name"]
    except Exception as e:
        raise api_error(e) from None


def item_status(client, access_token: str) -> dict:
    """Is this connection healthy? {ok, error_code, needs_reconnect, consent_expires}."""
    from plaid.model.item_get_request import ItemGetRequest

    try:
        item = client.item_get(ItemGetRequest(access_token=access_token))["item"]
    except Exception as e:
        err = api_error(e)
        return {
            "ok": False,
            "error_code": err.code,
            "needs_reconnect": err.code in RECONNECT_CODES,
            "consent_expires": None,
        }
    error = item.get("error")
    code = error.get("error_code") if error else None
    expires = item.get("consent_expiration_time")
    return {
        "ok": code is None,
        "error_code": code,
        "needs_reconnect": code in RECONNECT_CODES,
        "consent_expires": expires.isoformat() if expires else None,
    }


def default_start_date(today: date | None = None) -> str:
    """The old app's default: January 1 of this year (it combined this with manually uploaded CSVs)."""
    return date((today or date.today()).year, 1, 1).isoformat()
