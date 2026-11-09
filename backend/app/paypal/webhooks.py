import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from app.paypal.client import PayPalClient, get_paypal_client

router = APIRouter()
log = logging.getLogger("milestonepay.webhooks")

# Held in memory until the webhook_event table exists
_seen_event_ids: set[str] = set()


@router.post("/webhooks/paypal")
async def receive_paypal_event(
    request: Request, client: PayPalClient = Depends(get_paypal_client)
):
    try:
        event = json.loads(await request.body())
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Body is not valid JSON")

    headers = {name.lower(): value for name, value in request.headers.items()}
    if not await run_in_threadpool(client.verify_webhook, headers, event):
        raise HTTPException(status_code=400, detail="Webhook signature check failed")

    event_id = event.get("id", "")
    if event_id in _seen_event_ids:
        return {"status": "duplicate"}
    _seen_event_ids.add(event_id)

    log.info("PayPal event %s: %s", event_id, event.get("event_type"))
    return {"status": "ok"}
