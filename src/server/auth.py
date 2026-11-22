"""Who is calling.

nginx on pi5 runs the Google login (oauth2-proxy) and puts the verified address in X-Email, always
overwriting whatever the browser sent. This service listens on the LAN, so anything else on the LAN could
send that header too: it is believed only when the TCP peer is one of TRUSTED_PROXIES. Run uvicorn with
--no-proxy-headers, or request.client would be rewritten from X-Forwarded-For, which is client-controlled.
"""

from dataclasses import dataclass

from fastapi import HTTPException, Request


@dataclass(frozen=True)
class User:
    name: str  # the data directory
    email: str


def current_user(request: Request) -> User:
    settings = request.app.state.settings
    if settings.dev_user:
        return User(name=settings.dev_user, email="dev@localhost")
    peer = request.client.host if request.client else None
    if peer not in settings.trusted_proxies:
        raise HTTPException(403, "not reachable except through the login proxy")
    email = request.headers.get("x-email", "").strip().lower()
    if not email:
        raise HTTPException(401, "not logged in")
    name = settings.users.get(email)
    if not name:
        raise HTTPException(403, "this account has no expense data")
    return User(name=name, email=email)
