# Deployment

The app is deployed by the `velicanu/server` repo, not from here. This is how the pieces fit, so the two
repos stay in step.

```
browser --https--> nginx (pi5) --auth_request--> oauth2-proxy (Google login)
                       |
                       +--X-Email set by nginx--> this app on tess, 192.168.1.154:8094 (Docker, host network)
                                                     |
                                                     +--> ~/aa-viral-dragos-shared/data/<user>/   (Syncthing folder)
                                                     +--> OpenBao on pi5 (Plaid keys, read-only AppRole)
```

## What the server repo sets up (`iac/expense.tf`)

- DNS, the nginx site and `oauth2-proxy-expense` (only the emails in `local.expense_users`).
- On tess: `~/iac/expenses/compose.yaml`, `deploy.sh`, `users.json` (login email -> user) and a nightly
  `changes.db` backup. `ssh tess ~/iac/expenses/deploy.sh` checks out the branch in
  `local.expenses_branch`, builds the Dockerfile and starts it.
- Bao: `kv/expenses/plaid` (client id and secret), a read-only `expenses` policy and AppRole. The
  role id and secret id reach the container in `~/expenses/bao.env`.

## What the app expects (`src/server/settings.py`)

| Variable | Meaning |
|---|---|
| `DATA_ROOT` | directory with one subdirectory per user |
| `USERS_FILE` | JSON, login email -> user (the subdirectory name) |
| `TRUSTED_PROXIES` | addresses allowed to send `X-Email` (pi5's). Anything else gets 403. |
| `BAO_ADDR`, `BAO_ROLE_ID`, `BAO_SECRET_ID`, `BAO_KV_PATH` | where the Plaid keys are; optional, Plaid is off without them |
| `STATIC_DIR` | the built web app (set by the Dockerfile) |
| `LISTEN_HOST`, `PORT` | where to listen (tess's LAN address, 8094) |

Run it as **one process** (the pipeline lock and the data cache are in memory) and with
`--no-proxy-headers`, so the trusted-proxy check sees the real TCP peer. The Dockerfile does both.

## Data and Syncthing

`data/<user>/` is a Syncthing folder shared with other devices; tess is its only writer.
`expenses.db` is not synced (it is rebuilt from `raw/`; ignore patterns live in the server repo's
`iac/syncthing/desired.json`), `changes.db` is. The pipeline builds `expenses.db.tmp` next to the target
and renames it into place.

## Gotchas found the hard way

- `/tmp` in the container is a tmpfs and `/data` is a bind mount, so `os.replace` between them fails
  with `EXDEV`. Move across with `shutil.move`, or write the temp file next to the target.
- Don't split react and recharts into separate chunks (`manualChunks`): they import each other in a
  cycle and the page comes up blank.
- nginx's default read timeout is 60s; a Plaid pull or a large upload can take longer.
