"""Messages a client wrote on their portal page, as the freelancer sees them.

The client page only saves a message. The AI reads it only when the freelancer clicks Analyse,
through the same message reading as a pasted message, so its suggestions land in the usual inbox.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app import audit
from app.ai.messages import MessageAI, get_message_ai
from app.api.messages import MessageIn, create_message
from app.billing import one_at_a_time
from app.db import get_session
from app.models import ClientNote, Contract

router = APIRouter(prefix="/api")


def client_note_out(note: ClientNote) -> dict:
    return {
        "id": note.id,
        "body": note.body,
        "status": note.status,
        "message_id": note.message_id,
        "created_at": note.created_at,
    }


@router.get("/contracts/{contract_id}/client-messages")
def list_client_notes(contract_id: int, session: Session = Depends(get_session)):
    if session.get(Contract, contract_id) is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    notes = session.exec(
        select(ClientNote).where(ClientNote.contract_id == contract_id).order_by(ClientNote.id)
    ).all()
    return [client_note_out(n) for n in notes]


def _waiting_note(session: Session, note_id: int) -> ClientNote:
    note = session.get(ClientNote, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Message not found")
    if note.status != "waiting":
        raise HTTPException(status_code=409, detail="This message was already handled.")
    return note


@router.post("/client-messages/{note_id}/analyse")
def analyse_client_note(
    note_id: int, session: Session = Depends(get_session), ai: MessageAI = Depends(get_message_ai)
):
    """The freelancer asks the AI to read a client's message. One AI call; suggestions go to the inbox."""
    # a double click must not pay for the same AI reading twice
    with one_at_a_time("client_note", note_id):
        note = _waiting_note(session, note_id)
        result = create_message(MessageIn(contract_id=note.contract_id, body=note.body, sender="client"), session, ai)
        note.status = "analysed"
        note.message_id = result["message"]["id"]
        session.add(note)
        audit.record(session, note.contract_id, "user", "client_message_analysed", note_id=note.id)
        session.commit()
        return result


@router.post("/client-messages/{note_id}/dismiss")
def dismiss_client_note(note_id: int, session: Session = Depends(get_session)):
    """The freelancer handles the message themself, without the AI."""
    with one_at_a_time("client_note", note_id):
        note = _waiting_note(session, note_id)
        note.status = "dismissed"
        session.add(note)
        audit.record(session, note.contract_id, "user", "client_message_dismissed", note_id=note.id)
        session.commit()
        return client_note_out(note)
