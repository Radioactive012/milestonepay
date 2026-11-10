import json
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app import audit
from app.ai.contract import ContractAI, get_contract_ai
from app.ai.llm import AIError
from app.ai.schemas import ContractAnalysis
from app.ai.guardrails import check_analysis
from app.api.portal import file_list
from app.billing import invoice_milestone, one_at_a_time, sync_from_paypal, unlocked_milestone_ids
from app.db import get_session
from app.milestones import apply_deposit, move
from app.models import DEFAULT_HOURLY_RATE, AuditEntry, ChangeOrder, Contract, Invoice, Milestone, Reminder
from app.paypal.client import PayPalClient, PayPalError, get_paypal_client, paypal_reason

router = APIRouter(prefix="/api")

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_TEXT_CHARS = 100_000


def _money(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def contract_out(session: Session, contract: Contract) -> dict:
    milestones = session.exec(
        select(Milestone).where(Milestone.contract_id == contract.id).order_by(Milestone.position)
    ).all()
    invoices = session.exec(
        select(Invoice)
        .where(Invoice.milestone_id.in_([m.id for m in milestones]))
        .order_by(Invoice.created_at)
    ).all()
    latest_invoice = {inv.milestone_id: inv for inv in invoices}
    reminders: dict[int, list[dict]] = {}
    for r in session.exec(
        select(Reminder).where(Reminder.invoice_id.in_([inv.id for inv in invoices])).order_by(Reminder.id)
    ).all():
        reminders.setdefault(r.invoice_id, []).append({"stage": r.stage, "subject": r.subject, "sent_at": r.sent_at})
    files = file_list(session, [m.id for m in milestones], unlocked_milestone_ids(session, milestones))
    entries = session.exec(
        select(AuditEntry).where(AuditEntry.contract_id == contract.id).order_by(AuditEntry.id)
    ).all()
    change_orders = session.exec(
        select(ChangeOrder).where(ChangeOrder.contract_id == contract.id).order_by(ChangeOrder.id)
    ).all()
    return {
        "id": contract.id,
        "client_name": contract.client_name,
        "client_email": contract.client_email,
        "currency": contract.currency,
        "stated_total": _money(contract.stated_total),
        "milestone_total": _money(sum((m.amount for m in milestones), Decimal("0"))),
        "payment_terms_days": contract.payment_terms_days,
        "hourly_rate": _money(contract.hourly_rate),
        "status": contract.status,
        "portal_token": contract.portal_token,
        "risks": json.loads(contract.risks_json),
        "warnings": json.loads(contract.warnings_json),
        "ambiguities": json.loads(contract.ambiguities_json),
        "deposit_pct_suggested": contract.deposit_pct_suggested,
        "deposit_rationale": contract.deposit_rationale,
        "milestones": [
            {
                "id": m.id,
                "position": m.position,
                "title": m.title,
                "amount": _money(m.amount),
                "trigger": m.trigger,
                "trigger_description": m.trigger_description,
                "due_date": m.due_date,
                "revision_limit": m.revision_limit,
                "revisions_used": m.revisions_used,
                "is_deposit": m.is_deposit,
                "status": m.status,
                "invoice": _invoice_out(latest_invoice.get(m.id), reminders),
                "files": files.get(m.id, []),
            }
            for m in milestones
        ],
        "change_orders": [
            {
                "id": c.id,
                "description": c.description,
                "estimated_hours": str(c.estimated_hours),
                "price": _money(c.price),
                "milestone_id": c.milestone_id,
                "suggestion_id": c.suggestion_id,
            }
            for c in change_orders
        ],
        "audit": [
            {
                "actor": e.actor,
                "action": e.action,
                "details": json.loads(e.details_json),
                "at": e.created_at,
            }
            for e in entries
        ],
    }


def _invoice_out(invoice: Invoice | None, reminders: dict[int, list[dict]]) -> dict | None:
    if invoice is None:
        return None
    return {
        "id": invoice.id,
        "number": invoice.number,
        "paypal_invoice_id": invoice.paypal_invoice_id,
        "amount": _money(invoice.amount),
        "status": invoice.status,
        "payer_url": invoice.payer_url,
        "due_date": invoice.due_date,
        "paid_at": invoice.paid_at,
        "reminders": reminders.get(invoice.id, []),
    }


def _get_or_404(session: Session, model, item_id: int):
    item = session.get(model, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"{model.__name__} {item_id} not found")
    return item


@router.get("/contracts")
def list_contracts(session: Session = Depends(get_session)):
    contracts = session.exec(select(Contract).order_by(Contract.created_at.desc())).all()
    return [
        {
            "id": c.id,
            "client_name": c.client_name,
            "currency": c.currency,
            "status": c.status,
            "created_at": c.created_at,
        }
        for c in contracts
    ]


@router.post("/contracts", status_code=201)
def create_contract(
    client_email: str = Form(...),
    client_name: str | None = Form(None),
    text: str | None = Form(None),
    hourly_rate: Decimal | None = Form(None),
    file: UploadFile | None = File(None),
    session: Session = Depends(get_session),
    ai: ContractAI = Depends(get_contract_ai),
):
    text = (text or "").strip() or None
    if "@" not in client_email:
        raise HTTPException(status_code=422, detail="Enter the client's email address.")
    if hourly_rate is not None and not 0 < hourly_rate < 100_000:
        raise HTTPException(status_code=422, detail="Enter an hourly rate above zero.")
    if text is None and file is None:
        raise HTTPException(status_code=422, detail="Paste the contract text or upload a file.")
    if text and len(text) > MAX_TEXT_CHARS:
        raise HTTPException(status_code=422, detail="The contract text is too long (100,000 characters max).")

    file_bytes = media_type = None
    if file is not None:
        file_bytes = file.file.read(MAX_UPLOAD_BYTES + 1)
        if len(file_bytes) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=422, detail="The file is larger than 10 MB.")
        media_type = file.content_type

    try:
        analysis = ai.analyse(text=text, file_bytes=file_bytes, media_type=media_type)
    except AIError as error:
        raise HTTPException(status_code=502, detail=str(error))

    contract = save_analysed_contract(
        session, analysis, text or analysis.transcription, client_name, client_email, hourly_rate, actor="ai"
    )
    return contract_out(session, contract)


def save_analysed_contract(
    session: Session,
    analysis: ContractAnalysis,
    source: str,
    client_name: str | None,
    client_email: str,
    hourly_rate: Decimal | None,
    actor: str,
) -> Contract:
    """Run the code checks on an AI reading of a contract and save it as a draft."""
    checked = check_analysis(analysis, source)
    contract = Contract(
        client_name=(client_name or checked.client_name or "Client").strip(),
        client_email=client_email.strip(),
        currency=checked.currency,
        stated_total=checked.stated_total,
        payment_terms_days=checked.payment_terms_days,
        hourly_rate=(hourly_rate or DEFAULT_HOURLY_RATE).quantize(Decimal("0.01")),
        raw_text=source,
        risks_json=json.dumps([r.model_dump() for r in checked.risks]),
        warnings_json=json.dumps(checked.warnings),
        ambiguities_json=json.dumps(checked.ambiguities),
        deposit_pct_suggested=checked.deposit_pct,
        deposit_rationale=checked.deposit_rationale,
    )
    session.add(contract)
    session.flush()
    for position, m in enumerate(checked.milestones, start=1):
        session.add(Milestone(contract_id=contract.id, position=position, **asdict(m)))
    audit.record(
        session,
        contract.id,
        actor,
        "contract_analysed",
        milestones=len(checked.milestones),
        risks=len(checked.risks),
        warnings=len(checked.warnings),
    )
    session.commit()
    session.refresh(contract)
    return contract


@router.get("/contracts/{contract_id}")
def read_contract(contract_id: int, session: Session = Depends(get_session)):
    return contract_out(session, _get_or_404(session, Contract, contract_id))


class ContractUpdate(BaseModel):
    hourly_rate: Decimal = Field(gt=0, lt=100_000, max_digits=10, decimal_places=2)


@router.patch("/contracts/{contract_id}")
def update_contract(contract_id: int, changes: ContractUpdate, session: Session = Depends(get_session)):
    contract = _get_or_404(session, Contract, contract_id)
    contract.hourly_rate = changes.hourly_rate
    session.add(contract)
    audit.record(session, contract.id, "user", "hourly_rate_changed", hourly_rate=changes.hourly_rate)
    session.commit()
    return contract_out(session, contract)


class MilestoneUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    trigger: Literal["date", "event"] | None = None
    due_date: date | None = None
    trigger_description: str | None = None


@router.patch("/milestones/{milestone_id}")
def update_milestone(
    milestone_id: int, changes: MilestoneUpdate, session: Session = Depends(get_session)
):
    milestone = _get_or_404(session, Milestone, milestone_id)
    contract = session.get(Contract, milestone.contract_id)
    if milestone.status != "draft" or contract.status != "draft":
        raise HTTPException(status_code=409, detail="Milestones can only be edited before the contract is approved.")
    updates = changes.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(milestone, key, value)
    if milestone.trigger == "event":
        milestone.due_date = None
    session.add(milestone)
    audit.record(session, milestone.contract_id, "user", "milestone_edited", milestone_id=milestone.id, **updates)
    session.commit()
    return contract_out(session, session.get(Contract, milestone.contract_id))


class ApproveRequest(BaseModel):
    deposit_pct: int = Field(ge=0, le=50)


@router.post("/contracts/{contract_id}/approve")
def approve_contract(
    contract_id: int,
    body: ApproveRequest,
    session: Session = Depends(get_session),
    paypal: PayPalClient = Depends(get_paypal_client),
):
    # one approval at a time per contract, so a double click can't add two deposits
    with one_at_a_time("contract", contract_id):
        return _approve_contract(contract_id, body, session, paypal)


def _approve_contract(contract_id: int, body: ApproveRequest, session: Session, paypal: PayPalClient) -> dict:
    contract = _get_or_404(session, Contract, contract_id)
    if contract.status != "draft":
        raise HTTPException(status_code=409, detail="This contract is already approved.")
    milestones = session.exec(
        select(Milestone).where(Milestone.contract_id == contract.id).order_by(Milestone.position)
    ).all()
    if not milestones:
        raise HTTPException(status_code=422, detail="Add at least one milestone before approving.")
    undated = [m.title for m in milestones if m.trigger == "date" and m.due_date is None]
    if undated:
        raise HTTPException(status_code=422, detail=f"Add a due date to: {', '.join(undated)}")

    deposit = None
    if body.deposit_pct:
        deposit_amount, reduced = apply_deposit([m.amount for m in milestones], body.deposit_pct)
        for milestone, amount in zip(milestones, reduced):
            milestone.amount = amount
        deposit = Milestone(
            contract_id=contract.id,
            position=0,
            title=f"Deposit ({body.deposit_pct}%)",
            amount=deposit_amount,
            trigger="approval",
            trigger_description="Paid before work starts",
            is_deposit=True,
        )
        session.add(deposit)
        session.flush()

    for milestone in milestones:
        move(session, milestone, "scheduled" if milestone.trigger == "date" else "awaiting_trigger", "user")
    contract.status = "active"
    session.add(contract)
    audit.record(session, contract.id, "user", "contract_approved", deposit_pct=body.deposit_pct)
    session.commit()

    if deposit is not None:
        try:
            invoice_milestone(session, paypal, deposit, "user")
        except PayPalError as error:
            raise HTTPException(
                status_code=502,
                detail=f"Milestones approved, but PayPal didn't accept the deposit invoice: {paypal_reason(error)} Use Send invoice now to retry.",
            )
    return contract_out(session, contract)


@router.post("/milestones/{milestone_id}/invoice")
def send_milestone_invoice(
    milestone_id: int,
    session: Session = Depends(get_session),
    paypal: PayPalClient = Depends(get_paypal_client),
):
    milestone = _get_or_404(session, Milestone, milestone_id)
    contract = session.get(Contract, milestone.contract_id)
    # deposits and change orders are invoiced straight from draft, so a failed send can be retried
    ready = milestone.status in ("scheduled", "awaiting_trigger") or (
        milestone.trigger in ("approval", "change_order")
        and milestone.status == "draft"
        and contract.status == "active"
    )
    if not ready:
        raise HTTPException(status_code=409, detail=f"This milestone is {milestone.status} and can't be invoiced now.")
    try:
        invoice_milestone(session, paypal, milestone, "user")
    except PayPalError as error:
        raise HTTPException(status_code=502, detail=f"PayPal didn't accept the invoice: {paypal_reason(error)} Try again.")
    return contract_out(session, contract)


@router.post("/invoices/{invoice_id}/refresh")
def refresh_invoice(
    invoice_id: int,
    session: Session = Depends(get_session),
    paypal: PayPalClient = Depends(get_paypal_client),
):
    invoice = _get_or_404(session, Invoice, invoice_id)
    try:
        sync_from_paypal(session, paypal, invoice, "system")
    except PayPalError as error:
        raise HTTPException(status_code=502, detail=f"Couldn't read the invoice from PayPal: {paypal_reason(error)}")
    session.commit()
    milestone = session.get(Milestone, invoice.milestone_id)
    return contract_out(session, session.get(Contract, milestone.contract_id))
