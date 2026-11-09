from decimal import ROUND_HALF_UP, Decimal

from sqlmodel import Session

from app import audit
from app.models import Milestone

# The only status changes the app allows. Nothing else may write Milestone.status.
TRANSITIONS: dict[str, set[str]] = {
    "draft": {"scheduled", "awaiting_trigger", "invoiced", "cancelled"},
    "scheduled": {"invoiced", "cancelled"},
    "awaiting_trigger": {"invoiced", "cancelled"},
    "invoiced": {"paid", "overdue", "cancelled"},
    "overdue": {"paid", "cancelled"},
    "paid": set(),
    "cancelled": set(),
}

CENT = Decimal("0.01")


class InvalidTransition(Exception):
    pass


def move(session: Session, milestone: Milestone, new_status: str, actor: str, **details) -> None:
    if new_status not in TRANSITIONS.get(milestone.status, set()):
        raise InvalidTransition(
            f"Milestone '{milestone.title}' can't go from {milestone.status} to {new_status}"
        )
    old_status = milestone.status
    milestone.status = new_status
    session.add(milestone)
    audit.record(
        session,
        milestone.contract_id,
        actor,
        "milestone_status",
        milestone_id=milestone.id,
        title=milestone.title,
        old=old_status,
        new=new_status,
        **details,
    )


def record_revision(session: Session, milestone: Milestone, actor: str) -> bool:
    """Count one revision round the freelancer approved. True when it goes past the included rounds."""
    milestone.revisions_used += 1
    session.add(milestone)
    over_limit = milestone.revision_limit is not None and milestone.revisions_used > milestone.revision_limit
    audit.record(
        session,
        milestone.contract_id,
        actor,
        "revision_counted",
        milestone_id=milestone.id,
        used=milestone.revisions_used,
        limit=milestone.revision_limit,
        over_limit=over_limit,
    )
    return over_limit


def apply_deposit(amounts: list[Decimal], pct: int) -> tuple[Decimal, list[Decimal]]:
    """Split a deposit off the contract total, taking it evenly from every milestone.

    The deposit plus the reduced milestones always add up to the original total.
    """
    if not 0 <= pct <= 50:
        raise ValueError("Deposit must be between 0 and 50 percent")
    total = sum(amounts, Decimal("0"))
    deposit = (total * pct / 100).quantize(CENT, rounding=ROUND_HALF_UP)
    reduced = [(a * (100 - pct) / 100).quantize(CENT, rounding=ROUND_HALF_UP) for a in amounts]
    if reduced:
        # the leftover cent or two from rounding goes on the largest milestone, so none can hit zero
        largest = max(range(len(reduced)), key=lambda i: reduced[i])
        reduced[largest] += total - deposit - sum(reduced, Decimal("0"))
    return deposit, reduced
