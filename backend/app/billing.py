import secrets
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func
from sqlmodel import Session, select

from app import audit, clock
from app.milestones import CENT, TRANSITIONS, InvalidTransition, move
from app.models import ChangeOrder, Contract, Invoice, Milestone, utcnow
from app.paypal.client import PayPalClient
from app.paypal.invoices import create_invoice, get_invoice, payer_link, send_invoice

PAID_STATUSES = {"PAID", "MARKED_AS_PAID"}
REFUNDED_STATUSES = {"REFUNDED", "MARKED_AS_REFUNDED"}
MAX_CHANGE_ORDER_HOURS = Decimal("200")

_locks: dict[tuple, threading.Lock] = {}
_locks_guard = threading.Lock()


@contextmanager
def one_at_a_time(*key) -> Iterator[None]:
    """Let only one request at a time work on the same thing, so a double click can't bill twice.

    This works because the app runs as one server process (see the Dockerfile). Read anything
    the decision depends on after entering, not before.
    """
    with _locks_guard:
        lock = _locks.setdefault(key, threading.Lock())
    with lock:
        yield


def round_to_quarter_hour(hours: Decimal) -> Decimal:
    # quantize(Decimal("0.25")) would only round to 2 decimal places, not to quarters
    quarters = (hours * 4).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return (quarters / 4).quantize(CENT)


def _due_date(milestone: Milestone, contract: Contract, today: date) -> date:
    if milestone.trigger == "date" and milestone.due_date and milestone.due_date >= today:
        return milestone.due_date
    return today + timedelta(days=contract.payment_terms_days)


def invoice_milestone(
    session: Session, paypal: PayPalClient, milestone: Milestone, actor: str, today: date | None = None
) -> Invoice:
    """Create and send the PayPal invoice for a milestone. Safe to call again after a failure,
    and safe when two requests ask at once: the second gets the first one's invoice."""
    with one_at_a_time("milestone", milestone.id):
        return _invoice_milestone(session, paypal, milestone, actor, today)


def _invoice_milestone(
    session: Session, paypal: PayPalClient, milestone: Milestone, actor: str, today: date | None
) -> Invoice:
    existing = session.exec(
        select(Invoice).where(
            Invoice.milestone_id == milestone.id, Invoice.status.in_(["DRAFT", "SENT", "PAID"])
        )
    ).first()
    if existing and existing.status != "DRAFT":
        return existing
    if "invoiced" not in TRANSITIONS[milestone.status]:
        raise InvalidTransition(f"Milestone '{milestone.title}' can't be invoiced while {milestone.status}")

    contract = session.get(Contract, milestone.contract_id)
    invoice = existing
    if invoice is None:
        today = today or clock.today(session)
        number = f"MP-{contract.id:04d}-{milestone.position:02d}-{secrets.token_hex(2).upper()}"
        due = _due_date(milestone, contract, today)
        paypal_id = create_invoice(
            paypal,
            invoice_number=number,
            title=milestone.title,
            amount=milestone.amount,
            currency=contract.currency,
            client_email=contract.client_email,
            due_date=due,
            note=milestone.trigger_description or None,
        )
        invoice = Invoice(
            milestone_id=milestone.id,
            paypal_invoice_id=paypal_id,
            number=number,
            amount=milestone.amount,
            currency=contract.currency,
            due_date=due,
        )
        session.add(invoice)
        audit.record(session, contract.id, actor, "invoice_created", number=number, paypal_id=paypal_id)
        session.commit()

        send_invoice(paypal, invoice.paypal_invoice_id)
    elif get_invoice(paypal, invoice.paypal_invoice_id).get("status", "DRAFT") == "DRAFT":
        # a retry: PayPal may have sent it last time even though we didn't hear back
        send_invoice(paypal, invoice.paypal_invoice_id)
    invoice.payer_url = payer_link(get_invoice(paypal, invoice.paypal_invoice_id))
    invoice.status = "SENT"
    session.add(invoice)
    move(session, milestone, "invoiced", actor, invoice_number=invoice.number)
    audit.record(session, contract.id, actor, "invoice_sent", number=invoice.number, amount=invoice.amount)
    session.commit()
    session.refresh(invoice)
    return invoice


def approve_change_order(
    session: Session,
    paypal: PayPalClient,
    contract: Contract,
    *,
    description: str,
    estimated_hours: Decimal,
    actor: str,
    suggestion_id: int | None = None,
) -> ChangeOrder:
    """Turn approved extra work into its own milestone and send its PayPal invoice.

    The price is always hours x the contract's hourly rate, worked out here. Raises ValueError
    for bad input. If PayPal fails, the change order and its milestone are kept, and the
    invoice can be retried with the milestone invoice route. A suggestion only ever becomes one
    change order: approving it again returns the one already made.
    """
    with one_at_a_time("change_order", contract.id):
        if suggestion_id is not None:
            made = session.exec(select(ChangeOrder).where(ChangeOrder.suggestion_id == suggestion_id)).first()
            if made is not None:
                return made
        return _approve_change_order(
            session, paypal, contract, description=description, estimated_hours=estimated_hours,
            actor=actor, suggestion_id=suggestion_id,
        )


def _approve_change_order(
    session: Session,
    paypal: PayPalClient,
    contract: Contract,
    *,
    description: str,
    estimated_hours: Decimal,
    actor: str,
    suggestion_id: int | None,
) -> ChangeOrder:
    description = description.strip()
    if not description:
        raise ValueError("Describe the extra work.")
    if contract.status != "active":
        raise ValueError("Approve the contract before adding change orders.")
    hours = round_to_quarter_hour(Decimal(str(estimated_hours)))
    if not 0 < hours <= MAX_CHANGE_ORDER_HOURS:
        raise ValueError(f"Estimated hours must be more than 0 and at most {MAX_CHANGE_ORDER_HOURS}.")
    price = (hours * contract.hourly_rate).quantize(CENT, rounding=ROUND_HALF_UP)

    last_position = session.exec(
        select(func.max(Milestone.position)).where(Milestone.contract_id == contract.id)
    ).one()
    milestone = Milestone(
        contract_id=contract.id,
        position=(last_position or 0) + 1,
        title=f"Change order: {description}"[:200],
        amount=price,
        trigger="change_order",
        trigger_description=f"{hours} h at {contract.currency} {contract.hourly_rate}/h",
    )
    session.add(milestone)
    session.flush()
    order = ChangeOrder(
        contract_id=contract.id,
        suggestion_id=suggestion_id,
        description=description,
        estimated_hours=hours,
        price=price,
        milestone_id=milestone.id,
    )
    session.add(order)
    audit.record(
        session,
        contract.id,
        actor,
        "change_order_approved",
        description=description,
        hours=hours,
        price=price,
        suggestion_id=suggestion_id,
    )
    session.commit()
    session.refresh(order)
    invoice_milestone(session, paypal, milestone, actor)
    return order


def mark_invoice_paid(session: Session, invoice: Invoice, actor: str) -> None:
    # a late "paid" message must not undo a refund
    if invoice.status in ("PAID", "REFUNDED"):
        return
    invoice.status = "PAID"
    invoice.paid_at = utcnow()
    session.add(invoice)
    milestone = session.get(Milestone, invoice.milestone_id)
    if milestone.status in ("invoiced", "overdue"):
        move(session, milestone, "paid", actor, invoice_number=invoice.number)
    audit.record(session, milestone.contract_id, actor, "invoice_paid", number=invoice.number, amount=invoice.amount)


def mark_invoice_closed(session: Session, invoice: Invoice, status: str, actor: str) -> None:
    """status is CANCELLED (never paid) or REFUNDED (paid, then the money went back)."""
    if invoice.status == status or (status == "CANCELLED" and invoice.status in ("PAID", "REFUNDED")):
        return
    invoice.status = status
    session.add(invoice)
    milestone = session.get(Milestone, invoice.milestone_id)
    if status == "CANCELLED" and milestone.status in ("invoiced", "overdue"):
        move(session, milestone, "cancelled", actor, invoice_number=invoice.number)
    audit.record(session, milestone.contract_id, actor, f"invoice_{status.lower()}", number=invoice.number)


def sync_from_paypal(session: Session, paypal: PayPalClient, invoice: Invoice, actor: str) -> None:
    """Read the invoice from PayPal directly, for when a webhook was missed."""
    status = get_invoice(paypal, invoice.paypal_invoice_id).get("status", "")
    if status in PAID_STATUSES:
        mark_invoice_paid(session, invoice, actor)
    elif status == "CANCELLED":
        mark_invoice_closed(session, invoice, "CANCELLED", actor)
    elif status in REFUNDED_STATUSES:
        mark_invoice_closed(session, invoice, "REFUNDED", actor)


def unlocked_milestone_ids(session: Session, milestones: list[Milestone]) -> set[int]:
    """Milestones whose files the client may download: paid, and the money wasn't refunded."""
    paid = {m.id for m in milestones if m.status == "paid"}
    if not paid:
        return paid
    refunded = set(
        session.exec(
            select(Invoice.milestone_id).where(Invoice.milestone_id.in_(paid), Invoice.status == "REFUNDED")
        ).all()
    )
    return paid - refunded
