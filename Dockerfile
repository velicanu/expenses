# The expenses app: the React frontend (web/) built in one stage, the FastAPI server (src/) serving it in
# the next. Deployed on tess by velicanu/server (iac/files/tess/expenses/compose.yaml), which sets the
# environment described in src/server/settings.py.

FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    STATIC_DIR=/app/web \
    LISTEN_HOST=127.0.0.1 \
    PORT=8094
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/
COPY --from=web /web/dist ./web

# One process, on purpose: the per-user pipeline lock and the data cache live in memory.
# --no-proxy-headers: the login proxy's address is checked against the real TCP peer (src/server/auth.py);
# X-Forwarded-For must not be allowed to rewrite it.
CMD ["sh", "-c", "exec uvicorn server.app:create_app --factory --no-proxy-headers --host \"$LISTEN_HOST\" --port \"$PORT\""]

HEALTHCHECK --interval=60s --timeout=5s --start-period=15s \
  CMD ["sh", "-c", "python -c \"import os,urllib.request as u; u.urlopen('http://%s:%s/api/openapi.json' % (os.environ['LISTEN_HOST'], os.environ['PORT']), timeout=4)\""]
