# Development Tips

This doc is a dump of configs and commands to get streamlit deployed behind a nginx
server.

## nginx config

This conifg will run streamlit through nginx. Streamlit can either be accessible on the
LAN or on the same machine as nginx, just adjust the `192.168.1.123` ip appropriately.
```
        location /apps {
            proxy_pass http://192.168.1.123:8501/apps;
        }
        location ^~ /static {
            proxy_pass http://192.168.1.123:8501/apps/static;
        }
        location ^~ /healthz {
            proxy_pass http://192.168.1.123:8501/apps/healthz;
        }
        location ^~ /vendor {
            proxy_pass http://192.168.1.123:8501/apps/vendor;
        }
        location /apps/stream {
            proxy_pass http://192.168.1.123:8501/apps/stream;
            proxy_http_version 1.1;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header Host $host;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_read_timeout 86400;
        }
```

## Streamlit run command

Run streamlit via a command like the following:

```bash
streamlit run src/Home.py  --server.enableCORS false --server.enableXsrfProtection false --server.baseUrlPath /apps/
```

Note `/apps/` in the run command matches `/apps` in the nginx configuration above.

## Auth config

For auth to work you will need a `auth.yaml` file in the repo root directory. Don't
check this into github! It will look something like this:

```yaml
cookie:
  expiry_days: 30
  key: <key - random string>
  name: expense_app_cookie
credentials:
  usernames:
    user1:
      email: user1@example.com
      name: "user one"
      password: password_hash
preauthorized:
  emails:
  - user2@example.com
  - user3@example.com
```

Note: the emails field is only used to allow users to register, no confirmation or
password reset emails are sent.

The easiest way to get started is to start with a dummy credential, add the user you
want to create in preauthorized emails, and register the new user through the app and
let the app update the auth.yaml config file.
