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
