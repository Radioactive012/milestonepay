"""The evidence pack: one printable page with everything a freelancer needs if a client disputes a payment.

It shows what was agreed, what was delivered (with each file's SHA-256 fingerprint), what the client
approved and wrote, which invoices went out and were paid, and the full audit log. Read-only; no AI.
"""
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from html import escape

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlmodel import Session, select

from app.billing import unlocked_milestone_ids
from app.db import get_session
from app.models import AuditEntry, ClientNote, Contract, Deliverable, Invoice, Message, Milestone

router = APIRouter(prefix="/api")

ACTORS = {"user": "Freelancer", "client": "Client", "system": "MilestonePay", "ai": "AI", "paypal": "PayPal"}


def _when(value: datetime | None) -> str:
    return value.strftime("%d %b %Y, %H:%M UTC") if value else ""


def _table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return '<p class="none">None.</p>'
    head = "".join(f"<th>{escape(h)}</th>" for h in headers)
    head = f"<thead><tr>{head}</tr></thead>" if any(headers) else ""
    body = "".join("<tr>" + "".join(f"<td>{escape(str(cell))}</td>" for cell in row) + "</tr>" for row in rows)
    return f"<table>{head}<tbody>{body}</tbody></table>"


def _details(details_json: str) -> str:
    details = json.loads(details_json or "{}")
    return ", ".join(f"{key}: {value}" for key, value in details.items())


def evidence_html(session: Session, contract: Contract) -> str:
    money = lambda amount: f"{contract.currency} {amount}"  # noqa: E731
    milestones = session.exec(
        select(Milestone).where(Milestone.contract_id == contract.id).order_by(Milestone.position)
    ).all()
    by_id = {m.id: m for m in milestones}
    ids = list(by_id)
    unlocked = unlocked_milestone_ids(session, milestones)
    invoices = session.exec(select(Invoice).where(Invoice.milestone_id.in_(ids)).order_by(Invoice.created_at)).all()
    files = session.exec(select(Deliverable).where(Deliverable.milestone_id.in_(ids)).order_by(Deliverable.id)).all()
    audit = session.exec(
        select(AuditEntry).where(AuditEntry.contract_id == contract.id).order_by(AuditEntry.created_at, AuditEntry.id)
    ).all()
    approvals = [e for e in audit if e.action == "client_approved"]
    messages = session.exec(select(Message).where(Message.contract_id == contract.id).order_by(Message.id)).all()
    notes = session.exec(select(ClientNote).where(ClientNote.contract_id == contract.id).order_by(ClientNote.id)).all()
    from_client_page = {n.message_id for n in notes if n.message_id}
    approved_at = next((e.created_at for e in audit if e.action == "contract_approved"), None)
    paid_total = sum((i.amount for i in invoices if i.status == "PAID"), start=Decimal("0.00"))

    sections = [
        ("Summary", _table(["", ""], [
            ["Client", f"{contract.client_name} <{contract.client_email}>"],
            ["Project status", contract.status],
            ["Milestones approved by the freelancer", _when(approved_at) or "not yet"],
            ["Total of milestones", money(sum((m.amount for m in milestones if m.status != "cancelled"), start=Decimal("0.00")))],
            ["Paid through PayPal", money(paid_total)],
            ["Prepared", _when(datetime.now(timezone.utc)) + " (from MilestonePay's records)"],
        ])),
        ("Milestones", _table(
            ["#", "Milestone", "Amount", "When it's billed", "Status", "Client approved"],
            [[m.position + 1, m.title, money(m.amount), m.trigger_description or m.trigger, m.status,
              next((_when(e.created_at) for e in approvals if json.loads(e.details_json).get("milestone_id") == m.id), "")]
             for m in milestones],
        )),
        ("Invoices (PayPal sandbox)", _table(
            ["Invoice", "Milestone", "Amount", "Status", "Sent", "Due", "Paid"],
            [[i.number, by_id[i.milestone_id].title, money(i.amount), i.status, _when(i.created_at),
              i.due_date.strftime("%d %b %Y"), _when(i.paid_at)] for i in invoices],
        )),
        ("Files delivered", _table(
            ["File", "Milestone", "Size", "Uploaded", "SHA-256 fingerprint", "Client can download"],
            [[f.filename, by_id[f.milestone_id].title, f"{f.size_bytes:,} bytes", _when(f.uploaded_at),
              hashlib.sha256(f.data).hexdigest(), "yes" if f.milestone_id in unlocked else "no, locked until paid"]
             for f in files],
        )),
        ("What the client wrote", _table(
            ["When", "Where", "Message"],
            [[_when(n.created_at), "Client page" + (", read by the AI" if n.message_id else ""), n.body] for n in notes]
            # a client-page message the AI read is also saved in the inbox; list it once
            + [[_when(m.created_at), f"Inbox ({m.sender})", m.body] for m in messages if m.id not in from_client_page],
        )),
        ("Audit log: every action, who did it, and when", _table(
            ["When", "Who", "What", "Details"],
            [[_when(e.created_at), ACTORS.get(e.actor, e.actor), e.action.replace("_", " "), _details(e.details_json)]
             for e in audit],
        )),
        ("The contract text", f"<pre>{escape(contract.raw_text) or 'Not saved (uploaded as a file).'}</pre>"),
    ]
    body = "".join(f"<section><h2>{escape(title)}</h2>{content}</section>" for title, content in sections)
    title = f"Evidence pack: {contract.client_name}"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>
  body {{ font: 14px/1.5 system-ui, sans-serif; color: #0f172a; background: #fff; max-width: 960px; margin: 0 auto; padding: 24px 16px; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }} h2 {{ font-size: 16px; margin: 28px 0 8px; border-bottom: 1px solid #cbd5e1; padding-bottom: 4px; }}
  .lead {{ color: #475569; margin: 0 0 12px; }}
  table {{ width: 100%; border-collapse: collapse; }} th, td {{ text-align: left; vertical-align: top; padding: 6px 8px; border-bottom: 1px solid #e2e8f0; overflow-wrap: anywhere; }}
  th {{ background: #f1f5f9; font-weight: 600; }} pre {{ white-space: pre-wrap; background: #f8fafc; padding: 12px; border: 1px solid #e2e8f0; }}
  .none {{ color: #64748b; }} button {{ font: inherit; padding: 6px 14px; border-radius: 8px; border: 1px solid #94a3b8; background: #fff; cursor: pointer; }}
  @media print {{ button {{ display: none; }} body {{ padding: 0; }} }}
</style></head><body>
<h1>{escape(title)}</h1>
<p class="lead">Everything MilestonePay recorded for this project, for a payment dispute or your own records.
Times are in UTC. Each file's SHA-256 fingerprint proves which exact file was delivered.</p>
<button onclick="window.print()">Print or save as PDF</button>
{body}
</body></html>"""


@router.get("/contracts/{contract_id}/evidence", response_class=HTMLResponse)
def evidence_pack(contract_id: int, session: Session = Depends(get_session)):
    contract = session.get(Contract, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    return HTMLResponse(evidence_html(session, contract), headers={"Cache-Control": "no-store"})
