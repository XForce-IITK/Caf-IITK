"""Refresh token in an HttpOnly cookie for the web client (CAFIITK-207).

The web client sends `X-Token-Transport: cookie` on login, refresh and logout.
For those requests the refresh token is set as a cookie that page scripts
cannot read (HttpOnly), that the browser sends only to /api/v1/auth and never
on a cross-site request (SameSite=Strict), and only over HTTPS in production
(Secure); it is left out of the response body. The access token stays in the
client's memory, so a reload restores the session with one refresh call.

The custom header is also a CSRF guard: a cross-site page cannot add it without
a CORS preflight, which only the client's own origin passes (NFR-27).

Clients that do not send the header (the Android app, scripts) keep the token
in the JSON body as before and store it themselves.
"""

from fastapi import Request, Response

from app.core.config import get_settings
from app.modules.identity.schemas import TokenPair

TRANSPORT_HEADER = "X-Token-Transport"
COOKIE_TRANSPORT = "cookie"
REFRESH_COOKIE = "caf_refresh"
COOKIE_PATH = "/api/v1/auth"


def wants_cookie(request: Request) -> bool:
    return request.headers.get(TRANSPORT_HEADER, "").lower() == COOKIE_TRANSPORT


def presented_token(request: Request, body_token: str | None) -> str | None:
    """The token in the body, else the cookie, which counts only with the header."""
    if body_token is not None:
        return body_token
    if wants_cookie(request):
        return request.cookies.get(REFRESH_COOKIE)
    return None


def deliver(request: Request, response: Response, pair: TokenPair) -> TokenPair:
    """Move the refresh token into the cookie when the client asked for it."""
    if not wants_cookie(request) or pair.refresh_token is None:
        return pair
    settings = get_settings()
    response.set_cookie(
        REFRESH_COOKIE,
        pair.refresh_token,
        max_age=settings.refresh_ttl_days * 24 * 3600,
        path=COOKIE_PATH,
        secure=settings.is_production,
        httponly=True,
        samesite="strict",
    )
    return pair.model_copy(update={"refresh_token": None})


def clear(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        REFRESH_COOKIE,
        path=COOKIE_PATH,
        secure=settings.is_production,
        httponly=True,
        samesite="strict",
    )


def cleared_headers() -> dict[str, str]:
    """The Set-Cookie header that removes the cookie, for an error response."""
    response = Response()
    clear(response)
    return {"set-cookie": response.headers["set-cookie"]}
