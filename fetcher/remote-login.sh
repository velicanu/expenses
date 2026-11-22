#!/usr/bin/env bash
# The one-time login by hand: a virtual display (Xvfb) with a tiny window manager, seen through VNC and noVNC, with
# the browser open on the institution's sign-in page in its persistent profile.
#
# noVNC and VNC listen on 127.0.0.1 only (the container shares the host's network). From your computer:
#     ssh -L 6080:localhost:6080 tess
# then open http://localhost:6080/vnc.html?autoconnect=1&resize=scale and sign in. Anyone with a shell on tess can
# reach this port while it runs, so it only runs for the login and stops when it is done.
set -euo pipefail
export DISPLAY=:99
Xvfb :99 -screen 0 1280x900x24 -nolisten tcp &
sleep 1
fluxbox >/dev/null 2>&1 &
x11vnc -display :99 -localhost -forever -shared -nopw -quiet -rfbport 5900 >/dev/null 2>&1 &
websockify --web /usr/share/novnc 127.0.0.1:6080 127.0.0.1:5900 >/dev/null 2>&1 &
sleep 1
echo "noVNC ready on 127.0.0.1:6080  (ssh -L 6080:localhost:6080 tess ; http://localhost:6080/vnc.html?autoconnect=1&resize=scale)"
exec python -m fetcher login "$@"
