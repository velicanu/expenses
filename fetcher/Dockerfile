# The fetcher: a real (headed) Chromium under a virtual display, one script per institution, that logs in with a saved
# session and downloads the institution's own CSV export. A separate container from the app: its browser and its
# session data stay out of the app's image and out of the Syncthing folder. See velicanu/server docs/expense-direct-pulls.md.
#
# The base image has the browsers (chromium-1187 for playwright 1.55) but not the Python package: pin it to match.
FROM mcr.microsoft.com/playwright/python:v1.55.0-noble

# For the one-time hand login: a virtual display (Xvfb, in the base image), a tiny window manager, and a VNC server
# with a web front end (noVNC), reached over an SSH tunnel.
RUN apt-get update \
 && apt-get install -y --no-install-recommends x11vnc novnc websockify fluxbox xdotool \
 && rm -rf /var/lib/apt/lists/*

# fastapi + uvicorn (+ websockets, for the remote-browser stream) serve the credentials page. typing_extensions comes from Debian (no pip RECORD file), so pip cannot
# uninstall it to upgrade: install over it.
RUN pip install --no-cache-dir --ignore-installed typing_extensions playwright==1.55.0 fastapi uvicorn websockets pykeepass pyotp

# Real Google Chrome (not the bundled Chromium) for the hand login: a person drives it on the virtual desktop like Chrome on
# a remote desktop, with none of the automation switches Playwright adds. Playwright installs the stable .deb (/opt/google).
# It is whatever is current when the image is built.
RUN python -m playwright install chrome

WORKDIR /app
COPY . /app/fetcher/
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "-m", "fetcher"]
