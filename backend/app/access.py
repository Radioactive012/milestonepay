"""An optional password for the freelancer side of the hosted app.

When APP_PASSWORD is set, every page and API address asks for it, except what the client,
PayPal and Render need: the client page and its API, PayPal's webhook, the page's built
files and /health. The browser shows its own login box (HTTP Basic), so the screens need no
login page; any user name works. When APP_PASSWORD is empty, nothing is locked.
"""
import base64
import binascii
import secrets

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import get_settings

# the client's private link, PayPal and Render's health check must work without the password
OPEN_PREFIXES = ("/portal/", "/api/portal/", "/webhooks/", "/assets/")
OPEN_PATHS = {"/health"}


def is_open(path: str) -> bool:
    return path in OPEN_PATHS or path.startswith(OPEN_PREFIXES)


def password_matches(header: str | None, password: str) -> bool:
    if not header or not header.lower().startswith("basic "):
        return False
    try:
        decoded = base64.b64decode(header[6:].strip(), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return False
    _, _, given = decoded.partition(":")
    return secrets.compare_digest(given.encode(), password.encode())


def add_password_check(app: FastAPI) -> None:
    @app.middleware("http")
    async def check_password(request: Request, call_next):
        password = get_settings().app_password
        if password and not is_open(request.url.path):
            if not password_matches(request.headers.get("authorization"), password):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Enter the app password (any user name)."},
                    headers={"WWW-Authenticate": 'Basic realm="MilestonePay", charset="UTF-8"'},
                )
        return await call_next(request)
