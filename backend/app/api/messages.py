"""Client messages and the approval inbox.

The AI only proposes: a message is analysed, checked by code, and saved as suggestions.
Nothing happens to money until the freelancer approves a suggestion, and then Person A's
functions (invoice_milestone, approve_change_order, record_revision) do the work.
"""
import json
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError
from sqlmodel import Session, select

from app import audit
from app.ai.messages import POSSIBLE_BELOW, MessageAI, MessageAIError, check_message_analysis, get_message_ai
from app.api.contracts import contract_out
from app.billing import approve_change_order, invoice_milestone
from app.db import get_session
from app.milestones import record_revision
from app.models import ChangeOrder, Contract, Message, Milestone, Suggestion
from app.paypal.client import PayPalClient, PayPalError, get_paypal_client

router = APIRouter(prefix="/api")

MAX_MESSAGE_CHARS = 5000
# a milestone can only be billed because of a message while it is waiting for its trigger
WAITING = ("scheduled", "awaiting_trigger")


class MessageIn(BaseModel):
    contract_id: int
    body: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    sender: Literal["client", "freelancer", "pasted"] = "pasted"


class ApproveIn(BaseModel):
    """Optional edits when approving a change order."""

    hours: Decimal | None = Field(default=None, gt=0, le=200, max_digits=6, decimal_places=2)
    description: str | None = Field(default=None, min_length=1, max_length=200)


def _get_or_404(session: Session, model, item_id: int):
    item = session.get(model, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"{model.__name__} {item_id} not found")
    return item


def suggestion_out(s: Suggestion, message_body: str | None = None) -> dict:
    return {
        "id": s.id,
        "contract_id": s.contract_id,
        "message_id": s.message_id,
        "milestone_id": s.milestone_id,
        "type": s.type,
        "payload": json.loads(s.payload_json),
        "evidence_quote": s.evidence_quote,
        "confidence": s.confidence,
        # below the confidence bar the UI shows "Possible" and offers no ready-made action
        "possible": s.confidence < POSSIBLE_BELOW,
        "status": s.status,
        "message_body": message_body,
        "created_at": s.created_at,
    }


def message_out(m: Message, tags: list[dict] | None = None) -> dict:
    return {
        "id": m.id,
        "contract_id": m.contract_id,
        "sender": m.sender,
        "body": m.body,
        "analysis": json.loads(m.analysis_json),
        "tags": tags or [],
        "created_at": m.created_at,
    }


def _analyse(ai: MessageAI, body: str, contract: Contract, milestones: list[Milestone]):
    listed = [
        {
            "title": m.title,
            "status": m.status,
            "revisions_used": m.revisions_used,
            "revision_limit": "no limit" if m.revision_limit is None else m.revision_limit,
        }
        for m in milestones
    ]
    last: Exception | None = None
    for _ in range(2):  # one automatic retry, then give up
        try:
            return ai.analyse(message=body, contract_text=contract.raw_text, milestones=listed)
        except MessageAIError as error:
            last = error
        except ValidationError:
            last = MessageAIError("Couldn't read this message. Please handle it by hand.")
    raise HTTPException(status_code=502, detail=str(last))


@router.post("/messages", status_code=201)
def create_message(
    data: MessageIn, session: Session = Depends(get_session), ai: MessageAI = Depends(get_message_ai)
):
    contract = _get_or_404(session, Contract, data.contract_id)
    if contract.status != "active":
        raise HTTPException(status_code=409, detail="Approve the contract before adding messages.")
    body = data.body.strip()
    if not body:
        raise HTTPException(status_code=422, detail="The message is empty.")

    milestones = session.exec(
        select(Milestone).where(Milestone.contract_id == contract.id).order_by(Milestone.position)
    ).all()
    listed = [m for m in milestones if not m.is_deposit]
    by_title = {m.title.lower(): m for m in listed}

    analysis = _analyse(ai, body, contract, listed)
    checked = check_message_analysis(analysis, body, contract.raw_text, [m.title for m in listed], contract.hourly_rate)
    dropped = list(checked.dropped)

    message = Message(contract_id=contract.id, sender=data.sender, body=body)
    session.add(message)
    session.flush()
    suggestions: list[Suggestion] = []

    def propose(type_: str, milestone: Milestone | None, payload: dict, quote: str, confidence: float) -> None:
        suggestions.append(
            Suggestion(
                contract_id=contract.id,
                message_id=message.id,
                milestone_id=milestone.id if milestone else None,
                type=type_,
                payload_json=json.dumps(payload, default=str),
                evidence_quote=quote,
                confidence=confidence,
            )
        )

    for signal in checked.milestone_signals:
        milestone = by_title[signal.milestone_title.lower()]
        already = session.exec(
            select(Suggestion).where(
                Suggestion.milestone_id == milestone.id,
                Suggestion.type == "milestone_reached",
                Suggestion.status == "pending",
            )
        ).first()
        if milestone.status not in WAITING:
            dropped.append(f"'{milestone.title}' is already {milestone.status}, so no invoice was proposed.")
        elif already or any(s.milestone_id == milestone.id and s.type == "milestone_reached" for s in suggestions):
            dropped.append(f"'{milestone.title}' already has a pending suggestion.")
        else:
            propose(
                "milestone_reached",
                milestone,
                {"milestone_title": milestone.title, "amount": str(milestone.amount)},
                signal.quote,
                signal.confidence,
            )

    for item in checked.out_of_scope:
        propose(
            "scope_creep",
            None,
            {
                "description": item.request_quote.strip()[:200],
                "request_quote": item.request_quote,
                "contract_clause_quote": item.contract_clause_quote,
                "reason": item.reason,
                "estimated_hours": str(item.estimated_hours),
                "hourly_rate": str(contract.hourly_rate),
                "price": str(item.price),
            },
            item.request_quote,
            item.confidence,
        )

    for revision in checked.revision_requests:
        milestone = by_title[revision.milestone_title.lower()]
        limit = milestone.revision_limit
        propose(
            "extra_revision",
            milestone,
            {
                "milestone_title": milestone.title,
                "revisions_used": milestone.revisions_used,
                "revision_limit": limit,
                "over_limit": limit is not None and milestone.revisions_used + 1 > limit,
            },
            revision.quote,
            revision.confidence,
        )

    summary = {
        "milestone_signals": [s.model_dump() for s in checked.milestone_signals],
        "out_of_scope": [
            {"request_quote": o.request_quote, "estimated_hours": o.estimated_hours, "price": o.price}
            for o in checked.out_of_scope
        ],
        "revision_requests": [r.model_dump() for r in checked.revision_requests],
        "dropped": dropped,
    }
    message.analysis_json = json.dumps(summary, default=str)
    session.add(message)
    for s in suggestions:
        session.add(s)
    audit.record(
        session,
        contract.id,
        "ai",
        "message_analysed",
        message_id=message.id,
        suggestions=len(suggestions),
        dropped=len(dropped),
    )
    session.commit()
    for s in suggestions:
        session.refresh(s)
    return {
        "message": message_out(message, [{"type": s.type, "status": s.status} for s in suggestions]),
        "suggestions": [suggestion_out(s, body) for s in suggestions],
        "dropped": dropped,
    }


@router.get("/messages")
def list_messages(contract_id: int = Query(...), session: Session = Depends(get_session)):
    _get_or_404(session, Contract, contract_id)
    messages = session.exec(select(Message).where(Message.contract_id == contract_id).order_by(Message.id)).all()
    suggestions = session.exec(select(Suggestion).where(Suggestion.contract_id == contract_id)).all()
    return [
        message_out(m, [{"type": s.type, "status": s.status} for s in suggestions if s.message_id == m.id])
        for m in messages
    ]


@router.get("/suggestions")
def list_suggestions(
    status: Literal["pending", "approved", "dismissed"] = "pending",
    contract_id: int | None = None,
    session: Session = Depends(get_session),
):
    query = select(Suggestion).where(Suggestion.status == status).order_by(Suggestion.id.desc())
    if contract_id is not None:
        query = query.where(Suggestion.contract_id == contract_id)
    found = session.exec(query).all()
    bodies = {m.id: m.body for m in session.exec(select(Message)).all()}
    return [suggestion_out(s, bodies.get(s.message_id)) for s in found]


def _pending(session: Session, suggestion_id: int) -> Suggestion:
    s = _get_or_404(session, Suggestion, suggestion_id)
    if s.status != "pending":
        raise HTTPException(status_code=409, detail=f"This suggestion was already {s.status}.")
    return s


@router.post("/suggestions/{suggestion_id}/dismiss")
def dismiss_suggestion(suggestion_id: int, session: Session = Depends(get_session)):
    s = _pending(session, suggestion_id)
    s.status = "dismissed"
    session.add(s)
    audit.record(session, s.contract_id, "user", "suggestion_dismissed", suggestion_id=s.id, type=s.type)
    session.commit()
    return suggestion_out(s)


@router.post("/suggestions/{suggestion_id}/approve")
def approve_suggestion(
    suggestion_id: int,
    edits: ApproveIn | None = None,
    session: Session = Depends(get_session),
    paypal: PayPalClient = Depends(get_paypal_client),
):
    s = _pending(session, suggestion_id)
    if s.confidence < POSSIBLE_BELOW:
        raise HTTPException(
            status_code=409,
            detail="The AI isn't sure about this one. Dismiss it, or handle it by hand.",
        )
    contract = _get_or_404(session, Contract, s.contract_id)
    payload = json.loads(s.payload_json)
    milestone = session.get(Milestone, s.milestone_id) if s.milestone_id else None

    if s.type == "milestone_reached":
        if milestone is None:
            raise HTTPException(status_code=409, detail="The milestone for this suggestion no longer exists.")
        try:
            invoice_milestone(session, paypal, milestone, "user")
        except PayPalError as error:
            raise HTTPException(
                status_code=502,
                detail=f"PayPal didn't accept the invoice ({error.status_code}). Try approving again.",
            )
    elif s.type == "scope_creep":
        hours = edits.hours if edits and edits.hours is not None else Decimal(payload["estimated_hours"])
        description = edits.description if edits and edits.description else payload["description"]
        try:
            approve_change_order(
                session,
                paypal,
                contract,
                description=description,
                estimated_hours=hours,
                actor="user",
                suggestion_id=s.id,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error))
        except PayPalError as error:
            # the change order and its milestone were saved before PayPal failed
            if session.exec(select(ChangeOrder).where(ChangeOrder.suggestion_id == s.id)).first():
                s.status = "approved"
                session.add(s)
                audit.record(session, contract.id, "user", "suggestion_approved", suggestion_id=s.id, type=s.type)
                session.commit()
            raise HTTPException(
                status_code=502,
                detail=f"The change order is saved, but PayPal didn't accept the invoice ({error.status_code}). Use Send invoice on that milestone to retry.",
            )
    elif s.type == "extra_revision":
        if milestone is None:
            raise HTTPException(status_code=409, detail="The milestone for this suggestion no longer exists.")
        record_revision(session, milestone, "user")
    else:
        raise HTTPException(status_code=409, detail=f"Unknown suggestion type '{s.type}'.")

    s.status = "approved"
    session.add(s)
    audit.record(session, contract.id, "user", "suggestion_approved", suggestion_id=s.id, type=s.type)
    session.commit()
    session.refresh(s)
    return {"suggestion": suggestion_out(s), "contract": contract_out(session, contract)}
