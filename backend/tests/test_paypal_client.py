import json
from datetime import date
from decimal import Decimal

import httpx
import pytest

from app.config import Settings
from app.paypal.client import PayPalClient, PayPalError
from app.paypal.invoices import build_invoice_payload, create_invoice, payer_link


def make_settings(**overrides) -> Settings:
    values = dict(
        paypal_client_id="id",
        paypal_client_secret="secret",
        paypal_environment="SANDBOX",
        paypal_webhook_id="WH-1",
    )
    values.update(overrides)
    return Settings(_env_file=None, **values)


def make_client(handler) -> PayPalClient:
    return PayPalClient(make_settings(), transport=httpx.MockTransport(handler))


def test_live_environment_is_refused():
    with pytest.raises(RuntimeError):
        make_settings(paypal_environment="LIVE").paypal_base_url


def test_token_is_fetched_once_and_reused():
    token_calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/oauth2/token":
            token_calls.append(request)
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        assert request.headers["authorization"] == "Bearer tok"
        return httpx.Response(200, json={})

    client = make_client(handler)
    client.request("GET", "/v2/invoicing/invoices/INV2-1")
    client.request("GET", "/v2/invoicing/invoices/INV2-2")
    assert len(token_calls) == 1


def test_error_responses_raise_paypal_error():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        return httpx.Response(422, text="bad invoice")

    with pytest.raises(PayPalError) as error:
        make_client(handler).request("POST", "/v2/invoicing/invoices", json={})
    assert error.value.status_code == 422


def test_invoice_payload_has_two_decimal_amount_and_due_date():
    payload = build_invoice_payload(
        invoice_number="MP-1",
        title="Final logo",
        amount=Decimal("1400"),
        currency="USD",
        client_email="client@example.com",
        due_date=date(2026, 12, 1),
    )
    assert payload["items"][0]["unit_amount"] == {
        "currency_code": "USD",
        "value": "1400.00",
    }
    assert payload["detail"]["payment_term"]["due_date"] == "2026-12-01"
    assert payload["primary_recipients"][0]["billing_info"]["email_address"] == (
        "client@example.com"
    )


@pytest.mark.parametrize("amount", [Decimal("0"), Decimal("-5")])
def test_invoice_amount_must_be_positive(amount):
    with pytest.raises(ValueError):
        build_invoice_payload(
            invoice_number="MP-1",
            title="x",
            amount=amount,
            currency="USD",
            client_email="client@example.com",
            due_date=date(2026, 12, 1),
        )


def test_create_invoice_returns_id_from_href():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        return httpx.Response(
            201,
            json={
                "rel": "self",
                "href": "https://api-m.sandbox.paypal.com/v2/invoicing/invoices/INV2-ABCD",
                "method": "GET",
            },
        )

    invoice_id = create_invoice(
        make_client(handler),
        invoice_number="MP-1",
        title="Deposit",
        amount=Decimal("960"),
        currency="USD",
        client_email="client@example.com",
        due_date=date(2026, 12, 1),
    )
    assert invoice_id == "INV2-ABCD"


def test_payer_link_reads_recipient_view_url():
    invoice = {"detail": {"metadata": {"recipient_view_url": "https://pay.example/1"}}}
    assert payer_link(invoice) == "https://pay.example/1"
    assert payer_link({}) is None


@pytest.mark.parametrize("status,expected", [("SUCCESS", True), ("FAILURE", False)])
def test_verify_webhook_sends_headers_and_webhook_id(status, expected):
    sent = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        sent.update(json.loads(request.content))
        return httpx.Response(200, json={"verification_status": status})

    headers = {
        "paypal-auth-algo": "SHA256withRSA",
        "paypal-cert-url": "https://api.sandbox.paypal.com/cert",
        "paypal-transmission-id": "t-1",
        "paypal-transmission-sig": "sig",
        "paypal-transmission-time": "2026-11-10T10:00:00Z",
    }
    result = make_client(handler).verify_webhook(headers, {"id": "WH-EVT-1"})
    assert result is expected
    assert sent["webhook_id"] == "WH-1"
    assert sent["transmission_id"] == "t-1"
    assert sent["webhook_event"] == {"id": "WH-EVT-1"}


def test_missing_keys_give_a_clear_error_without_calling_paypal():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("PayPal should not be called without keys")

    client = PayPalClient(
        make_settings(paypal_client_id="", paypal_client_secret=""), transport=httpx.MockTransport(handler)
    )
    with pytest.raises(PayPalError) as error:
        client.request("GET", "/v2/invoicing/invoices/INV2-1")
    assert "keys are missing" in str(error.value)


def test_network_failure_becomes_paypal_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no internet")

    with pytest.raises(PayPalError) as error:
        make_client(handler).request("GET", "/v2/invoicing/invoices/INV2-1")
    assert error.value.status_code == 503
