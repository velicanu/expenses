# Plaid integration

Plaid is an external service that lets you connect to most credit card accounts through
their api. This expenses app only requires this plaid service to be running in order to
perform the `Link Account` action to get a token for pulling transactions. After
obtaining that token this plaid service is no longer required and can be stopped.

## Requirements

* Docker
* Plaid client id and secret

To use Plaid you first need to create an account with them and get a development
environment created, which comes with 100 credit card account connections to use. Once
you have the development environment, set the environment variables `PLAID_SECRET` and
`PLAID_CLIENT_ID` in your shell.

## Run

After configuring the plaid keys and starting docker you can start the plaid service
via:

```bash
./start.sh
```
Then you can go to the expenses UI and use the `Link Account` button.

To stop this plaid service run the stop script:
```bash
./stop.sh
```
