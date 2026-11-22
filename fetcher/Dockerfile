# The fetcher: a real (headed) Chromium under a virtual display, one script per institution, that logs in with a saved
# session and downloads the institution's own CSV export. A separate container from the app: its browser and its
# session data stay out of the app's image and out of the Syncthing folder. See velicanu/server docs/expense-direct-pulls.md.
#
# The base image has the browsers (chromium-1187 for playwright 1.55) but not the Python package: pin it to match.
FROM mcr.microsoft.com/playwright/python:v1.55.0-noble

# For the one-time hand login: a virtual display (Xvfb, in the base image), a tiny window manager, and a VNC server
# with a web front end (noVNC), reached over an SSH tunnel.
RUN apt-get update \
 && apt-get install -y --no-install-recommends x11vnc novnc websockify fluxbox \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir playwright==1.55.0 pykeepass pyotp

WORKDIR /app
COPY . /app/fetcher/
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "-m", "fetcher"]
