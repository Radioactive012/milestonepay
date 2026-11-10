from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.paypal.client import PayPalClient


def _money(amount: Decimal, currency: str) -> dict:
    if amount <= 0:
        raise ValueError("Invoice amount must be greater than zero")
    value = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {"currency_code": currency, "value": str(value)}


def build_invoice_payload(
    *,
    invoice_number: str,
    title: str,
    amount: Decimal,
    currency: str,
    client_email: str,
    due_date: date,
    note: str | None = None,
) -> dict:
    detail = {
        "invoice_number": invoice_number,
        "currency_code": currency,
        "payment_term": {
            "term_type": "DUE_ON_DATE_SPECIFIED",
            "due_date": due_date.isoformat(),
        },
    }
    if note:
        detail["note"] = note
    return {
        "detail": detail,
        "primary_recipients": [{"billing_info": {"email_address": client_email}}],
        "items": [
            {"name": title, "quantity": "1", "unit_amount": _money(amount, currency)}
        ],
    }


def create_invoice(client: PayPalClient, **payload_args) -> str:
    created = client.request(
        "POST", "/v2/invoicing/invoices", json=build_invoice_payload(**payload_args)
    )
    return created_invoice_id(created)


def created_invoice_id(created: dict) -> str:
    """The new invoice's id. PayPal answers with the invoice itself, a link to it, or a list
    of links, depending on the account's settings; accept all three."""
    if created.get("id"):
        return created["id"]
    links = [created] if created.get("href") else created.get("links", [])
    for link in links:
        if link.get("rel", "self") == "self" and link.get("href"):
            return link["href"].rstrip("/").rsplit("/", 1)[-1]
    raise ValueError(f"PayPal didn't say which invoice it created: {str(created)[:200]}")


def send_invoice(client: PayPalClient, invoice_id: str) -> None:
    client.request(
        "POST",
        f"/v2/invoicing/invoices/{invoice_id}/send",
        json={"send_to_recipient": True, "send_to_invoicer": False},
    )


def get_invoice(client: PayPalClient, invoice_id: str) -> dict:
    return client.request("GET", f"/v2/invoicing/invoices/{invoice_id}")


def remind_invoice(
    client: PayPalClient, invoice_id: str, subject: str, note: str
) -> None:
    client.request(
        "POST",
        f"/v2/invoicing/invoices/{invoice_id}/remind",
        json={"subject": subject, "note": note, "send_to_invoicer": False},
    )


def payer_link(invoice: dict) -> str | None:
    return invoice.get("detail", {}).get("metadata", {}).get("recipient_view_url")
