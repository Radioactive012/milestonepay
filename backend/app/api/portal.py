import json
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy.orm import defer
from sqlmodel import Session, select

from app import audit
from app.billing import invoice_milestone, unlocked_milestone_ids
from app.db import get_session
from app.files import MAX_FILE_BYTES, make_preview, safe_filename
from app.models import AuditEntry, Contract, Deliverable, Invoice, Milestone
from app.paypal.client import PayPalClient, PayPalError, get_paypal_client

router = APIRouter(prefix="/api")


def file_list(session: Session, milestone_ids: list[int], paid_ids: set[int]) -> dict[int, list[dict]]:
    """File details by milestone, without loading the file contents."""
    rows = session.exec(
        select(Deliverable)
        .where(Deliverable.milestone_id.in_(milestone_ids))
        .options(defer(Deliverable.data), defer(Deliverable.preview))
        .order_by(Deliverable.id)
    ).all()
    has_preview = set(
        session.exec(
            select(Deliverable.id).where(
                Deliverable.milestone_id.in_(milestone_ids), Deliverable.preview.is_not(None)
            )
        ).all()
    )
    files: dict[int, list[dict]] = {}
    for row in rows:
        files.setdefault(row.milestone_id, []).append(
            {
                "id": row.id,
                "filename": row.filename,
                "content_type": row.content_type,
                "size_bytes": row.size_bytes,
                "has_preview": row.id in has_preview,
                "locked": row.milestone_id not in paid_ids,
            }
        )
    return files


def _download(deliverable: Deliverable) -> Response:
    return Response(
        content=deliverable.data,
        media_type=deliverable.content_type,
        # always a download, never shown as a page, so an uploaded HTML or SVG file can't run
        headers={
            "Content-Disposition": f'attachment; filename="{deliverable.filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


# Freelancer side


@router.post("/milestones/{milestone_id}/files", status_code=201)
def upload_file(milestone_id: int, file: UploadFile = File(...), session: Session = Depends(get_session)):
    milestone = session.get(Milestone, milestone_id)
    if milestone is None:
        raise HTTPException(status_code=404, detail=f"Milestone {milestone_id} not found")
    if milestone.status == "cancelled":
        raise HTTPException(status_code=409, detail="This milestone is cancelled.")
    data = file.file.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(status_code=422, detail="The file is larger than 10 MB.")
    if not data:
        raise HTTPException(status_code=422, detail="The file is empty.")
    content_type = file.content_type or "application/octet-stream"
    deliverable = Deliverable(
        milestone_id=milestone.id,
        filename=safe_filename(file.filename),
        content_type=content_type,
        size_bytes=len(data),
        data=data,
        preview=make_preview(data, content_type),
    )
    session.add(deliverable)
    audit.record(
        session, milestone.contract_id, "user", "file_uploaded",
        milestone_id=milestone.id, filename=deliverable.filename, size_bytes=len(data),
    )
    session.commit()
    return {"id": deliverable.id, "filename": deliverable.filename, "has_preview": deliverable.preview is not None}


@router.get("/files/{file_id}")
def download_own_file(file_id: int, session: Session = Depends(get_session)):
    deliverable = session.get(Deliverable, file_id)
    if deliverable is None:
        raise HTTPException(status_code=404, detail=f"File {file_id} not found")
    return _download(deliverable)


# Client side: everything is reached through the contract's private portal link


def _contract_for(session: Session, token: str) -> Contract:
    contract = session.exec(select(Contract).where(Contract.portal_token == token)).first()
    if contract is None:
        raise HTTPException(status_code=404, detail="This link isn't valid. Ask the freelancer for a new one.")
    return contract


def _milestone_in(session: Session, contract: Contract, milestone_id: int) -> Milestone:
    milestone = session.get(Milestone, milestone_id)
    if milestone is None or milestone.contract_id != contract.id:
        raise HTTPException(status_code=404, detail="Milestone not found")
    return milestone


def _file_in(session: Session, contract: Contract, file_id: int) -> tuple[Deliverable, Milestone]:
    deliverable = session.get(Deliverable, file_id)
    milestone = session.get(Milestone, deliverable.milestone_id) if deliverable else None
    if milestone is None or milestone.contract_id != contract.id:
        raise HTTPException(status_code=404, detail="File not found")
    return deliverable, milestone


def client_approved_ids(session: Session, contract: Contract) -> set[int]:
    """Milestones the client has already approved, read from the audit log."""
    entries = session.exec(
        select(AuditEntry.details_json).where(
            AuditEntry.contract_id == contract.id, AuditEntry.action == "client_approved"
        )
    ).all()
    return {json.loads(details).get("milestone_id") for details in entries}


def _can_approve(milestone: Milestone, approved: set[int]) -> bool:
    if milestone.is_deposit:
        return False
    # an event milestone stays approvable until its invoice goes out, so a failed one can be retried
    if milestone.status == "awaiting_trigger":
        return True
    return milestone.status == "scheduled" and milestone.id not in approved


def portal_view(session: Session, contract: Contract) -> dict:
    view = {"client_name": contract.client_name, "currency": contract.currency, "status": contract.status}
    if contract.status == "draft":
        return view | {"milestones": [], "total": "0.00", "paid": "0.00", "outstanding": "0.00"}

    milestones = session.exec(
        select(Milestone)
        .where(Milestone.contract_id == contract.id, Milestone.status != "cancelled")
        .order_by(Milestone.position)
    ).all()
    ids = [m.id for m in milestones]
    invoices = session.exec(select(Invoice).where(Invoice.milestone_id.in_(ids)).order_by(Invoice.created_at)).all()
    latest = {inv.milestone_id: inv for inv in invoices}
    paid_ids = unlocked_milestone_ids(session, milestones)
    files = file_list(session, ids, paid_ids)
    approved = client_approved_ids(session, contract)
    total = sum((m.amount for m in milestones), Decimal("0.00"))
    paid = sum((m.amount for m in milestones if m.id in paid_ids), Decimal("0.00"))
    return view | {
        "total": str(total),
        "paid": str(paid),
        "outstanding": str(total - paid),
        "milestones": [
            {
                "id": m.id,
                "title": m.title,
                "amount": str(m.amount),
                "status": m.status,
                "due_date": m.due_date,
                "trigger_description": m.trigger_description,
                "is_deposit": m.is_deposit,
                "can_approve": _can_approve(m, approved),
                "approved_by_client": m.id in approved,
                "invoice": None
                if m.id not in latest
                else {
                    "number": latest[m.id].number,
                    "amount": str(latest[m.id].amount),
                    "status": latest[m.id].status,
                    "payer_url": latest[m.id].payer_url,
                    "due_date": latest[m.id].due_date,
                },
                "files": files.get(m.id, []),
            }
            for m in milestones
        ],
    }


@router.get("/portal/{token}")
def read_portal(token: str, session: Session = Depends(get_session)):
    return portal_view(session, _contract_for(session, token))


@router.post("/portal/{token}/milestones/{milestone_id}/approve")
def client_approves(
    token: str,
    milestone_id: int,
    session: Session = Depends(get_session),
    paypal: PayPalClient = Depends(get_paypal_client),
):
    """The client confirms a milestone's work is accepted. Event milestones are invoiced at once."""
    contract = _contract_for(session, token)
    milestone = _milestone_in(session, contract, milestone_id)
    if milestone.is_deposit or milestone.status not in ("awaiting_trigger", "scheduled"):
        raise HTTPException(status_code=409, detail="This milestone doesn't need your approval now.")
    if not _can_approve(milestone, client_approved_ids(session, contract)):
        return portal_view(session, contract)  # already approved; nothing more to do

    audit.record(session, contract.id, "client", "client_approved", milestone_id=milestone.id, title=milestone.title)
    session.commit()
    if milestone.status == "awaiting_trigger":
        try:
            invoice_milestone(session, paypal, milestone, "client")
        except PayPalError:
            # the client doesn't need PayPal's technical reason; the freelancer sees it on their side
            session.rollback()
            raise HTTPException(
                status_code=502,
                detail="Your approval is saved, but the invoice couldn't be created just now. "
                "Please try again in a minute, or let your freelancer know.",
            )
    return portal_view(session, contract)


@router.get("/portal/{token}/files/{file_id}/preview")
def client_preview(token: str, file_id: int, session: Session = Depends(get_session)):
    deliverable, _ = _file_in(session, _contract_for(session, token), file_id)
    if deliverable.preview is None:
        raise HTTPException(status_code=404, detail="There's no preview for this file type.")
    return Response(content=deliverable.preview, media_type="image/jpeg")


@router.get("/portal/{token}/files/{file_id}")
def client_download(token: str, file_id: int, session: Session = Depends(get_session)):
    contract = _contract_for(session, token)
    deliverable, milestone = _file_in(session, contract, file_id)
    if milestone.id not in unlocked_milestone_ids(session, [milestone]):
        raise HTTPException(status_code=402, detail="Pay this milestone's invoice to download the full file.")
    audit.record(
        session, contract.id, "client", "file_downloaded", milestone_id=milestone.id, filename=deliverable.filename
    )
    session.commit()
    return _download(deliverable)
