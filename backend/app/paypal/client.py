import json
import time
from functools import lru_cache

import httpx

from app.config import Settings, get_settings


class PayPalError(Exception):
    def __init__(self, status_code: int, body: str):
        super().__init__(f"PayPal returned {status_code}: {body}")
        self.status_code = status_code
        self.body = body


def paypal_reason(error: PayPalError) -> str:
    """A short, readable reason for a PayPal failure, for messages shown to people."""
    body = error.body.strip()
    if body.startswith("{"):
        try:
            data = json.loads(body)
            body = data.get("message") or data.get("error_description") or data.get("name") or body
        except ValueError:
            pass
    return f"{body[:200].rstrip('.')} (PayPal {error.status_code})."


class PayPalClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self._settings = settings
        self._http = httpx.Client(
            base_url=settings.paypal_base_url, timeout=20, transport=transport
        )
        self._token: str | None = None
        self._token_expires_at = 0.0

    def _access_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token
        if not (self._settings.paypal_client_id and self._settings.paypal_client_secret):
            raise PayPalError(
                401, "PayPal sandbox keys are missing. Add PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET to .env."
            )
        response = self._send(
            "POST",
            "/v1/oauth2/token",
            auth=(self._settings.paypal_client_id, self._settings.paypal_client_secret),
            data={"grant_type": "client_credentials"},
            headers={"Accept": "application/json"},
        )
        self._raise_for_error(response)
        body = response.json()
        self._token = body["access_token"]
        self._token_expires_at = time.time() + int(body["expires_in"])
        return self._token

    @staticmethod
    def _raise_for_error(response: httpx.Response) -> None:
        if response.status_code >= 400:
            raise PayPalError(response.status_code, response.text)

    def _send(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            return self._http.request(method, path, **kwargs)
        except httpx.HTTPError as error:
            raise PayPalError(503, f"Couldn't reach PayPal: {error.__class__.__name__}") from error

    def request(self, method: str, path: str, **kwargs) -> dict:
        headers = {"Authorization": f"Bearer {self._access_token()}"}
        headers.update(kwargs.pop("headers", {}))
        response = self._send(method, path, headers=headers, **kwargs)
        self._raise_for_error(response)
        return response.json() if response.content else {}

    def verify_webhook(self, headers: dict[str, str], raw_body: bytes) -> bool:
        """Ask PayPal whether an event really came from PayPal.

        The event goes back exactly as it arrived. PayPal checks a signature over the original
        text, so re-writing it (key order, spacing, how accents are escaped) can make a real
        event fail the check.
        """
        fields = {
            "auth_algo": headers.get("paypal-auth-algo", ""),
            "cert_url": headers.get("paypal-cert-url", ""),
            "transmission_id": headers.get("paypal-transmission-id", ""),
            "transmission_sig": headers.get("paypal-transmission-sig", ""),
            "transmission_time": headers.get("paypal-transmission-time", ""),
            "webhook_id": self._settings.paypal_webhook_id,
        }
        body = json.dumps(fields)[:-1].encode() + b', "webhook_event": ' + raw_body.strip() + b"}"
        result = self.request(
            "POST",
            "/v1/notifications/verify-webhook-signature",
            content=body,
            headers={"Content-Type": "application/json"},
        )
        return result.get("verification_status") == "SUCCESS"


@lru_cache
def get_paypal_client() -> PayPalClient:
    return PayPalClient(get_settings())
