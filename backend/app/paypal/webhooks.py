import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool

from app.billing import mark_invoice_closed, mark_invoice_paid
from app.db import get_session
from app.models import Invoice, WebhookEvent
from app.paypal.client import PayPalClient, get_paypal_client

router = APIRouter()
log = logging.getLogger("milestonepay.webhooks")


def handle_event(session: Session, event: dict) -> str:
    event_id = event.get("id")
    if not event_id:
        return "ignored"
    if session.get(WebhookEvent, event_id):
        return "duplicate"

    event_type = event.get("event_type", "")
    session.add(WebhookEvent(id=event_id, event_type=event_type, payload_json=json.dumps(event)))

    resource = event.get("resource") or {}
    paypal_id = (resource.get("invoice") or resource).get("id")
    invoice = None
    if paypal_id:
        invoice = session.exec(select(Invoice).where(Invoice.paypal_invoice_id == paypal_id)).first()
    if invoice:
        if event_type == "INVOICING.INVOICE.PAID":
            mark_invoice_paid(session, invoice, "paypal")
        elif event_type == "INVOICING.INVOICE.CANCELLED":
            mark_invoice_closed(session, invoice, "CANCELLED", "paypal")
        elif event_type == "INVOICING.INVOICE.REFUNDED":
            mark_invoice_closed(session, invoice, "REFUNDED", "paypal")

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return "duplicate"
    log.info("PayPal event %s (%s) for invoice %s", event_id, event_type, paypal_id)
    return "ok"


@router.post("/webhooks/paypal")
async def receive_paypal_event(
    request: Request,
    client: PayPalClient = Depends(get_paypal_client),
    session: Session = Depends(get_session),
):
    try:
        event = json.loads(await request.body())
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Body is not valid JSON")

    headers = {name.lower(): value for name, value in request.headers.items()}
    if not await run_in_threadpool(client.verify_webhook, headers, event):
        raise HTTPException(status_code=400, detail="Webhook signature check failed")

    return {"status": await run_in_threadpool(handle_event, session, event)}
