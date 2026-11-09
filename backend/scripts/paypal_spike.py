"""Day 1 check: create, send and pay one invoice in the PayPal sandbox.

Run from the backend folder:
    python -m scripts.paypal_spike <sandbox-personal-account-email>
"""
import sys
import time
from datetime import date, timedelta
from decimal import Decimal

from app.config import get_settings
from app.paypal.client import PayPalClient
from app.paypal.invoices import create_invoice, get_invoice, payer_link, send_invoice


def main(client_email: str) -> None:
    client = PayPalClient(get_settings())
    invoice_id = create_invoice(
        client,
        invoice_number=f"MP-SPIKE-{int(time.time())}",
        title="Sketches milestone",
        amount=Decimal("800.00"),
        currency="USD",
        client_email=client_email,
        due_date=date.today() + timedelta(days=15),
        note="Test invoice from the MilestonePay spike script",
    )
    print("Created draft invoice:", invoice_id)
    send_invoice(client, invoice_id)
    invoice = get_invoice(client, invoice_id)
    print("Status after sending:", invoice["status"])
    print("Open this link logged in as the sandbox personal account and pay:")
    print(payer_link(invoice))

    for _ in range(60):
        time.sleep(5)
        status = get_invoice(client, invoice_id)["status"]
        print("Status:", status)
        if status == "PAID":
            print("Done: the invoice was paid.")
            return
    print("Stopped waiting. Check the invoice in the sandbox dashboard.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
