import secrets
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Column, LargeBinary, UniqueConstraint
from sqlmodel import Field, SQLModel


DEFAULT_HOURLY_RATE = Decimal("40.00")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Contract(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    client_name: str
    client_email: str
    currency: str = "USD"
    stated_total: Decimal | None = Field(default=None, max_digits=12, decimal_places=2)
    payment_terms_days: int = 15
    # used to price change orders: estimated hours x this rate
    hourly_rate: Decimal = Field(default=DEFAULT_HOURLY_RATE, max_digits=10, decimal_places=2)
    raw_text: str = ""
    risks_json: str = "[]"
    warnings_json: str = "[]"
    ambiguities_json: str = "[]"
    deposit_pct_suggested: int = 0
    deposit_rationale: str = ""
    # draft until the freelancer approves the milestones, then active
    status: str = "draft"
    portal_token: str = Field(default_factory=lambda: secrets.token_urlsafe(16), index=True)
    created_at: datetime = Field(default_factory=utcnow)


class Milestone(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    contract_id: int = Field(foreign_key="contract.id", index=True)
    position: int
    title: str
    amount: Decimal = Field(max_digits=12, decimal_places=2)
    # date, event, approval (the deposit) or change_order
    trigger: str
    trigger_description: str = ""
    due_date: date | None = None
    revision_limit: int | None = None
    # only increased when the freelancer approves a revision suggestion
    revisions_used: int = 0
    is_deposit: bool = False
    status: str = "draft"


class Invoice(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    milestone_id: int = Field(foreign_key="milestone.id", index=True)
    paypal_invoice_id: str = Field(unique=True, index=True)
    number: str = Field(unique=True)
    amount: Decimal = Field(max_digits=12, decimal_places=2)
    currency: str
    # mirrors PayPal: DRAFT, SENT, PAID, CANCELLED, REFUNDED
    status: str = "DRAFT"
    payer_url: str | None = None
    due_date: date
    created_at: datetime = Field(default_factory=utcnow)
    paid_at: datetime | None = None


class Message(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    contract_id: int = Field(foreign_key="contract.id", index=True)
    # client, freelancer or pasted
    sender: str
    body: str
    analysis_json: str = "{}"
    created_at: datetime = Field(default_factory=utcnow)


class Suggestion(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    contract_id: int = Field(foreign_key="contract.id", index=True)
    message_id: int | None = Field(default=None, foreign_key="message.id")
    milestone_id: int | None = Field(default=None, foreign_key="milestone.id")
    # milestone_reached, scope_creep or extra_revision
    type: str
    payload_json: str = "{}"
    evidence_quote: str = ""
    confidence: float = 1.0
    # pending, approved or dismissed
    status: str = "pending"
    created_at: datetime = Field(default_factory=utcnow)


class ChangeOrder(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    contract_id: int = Field(foreign_key="contract.id", index=True)
    suggestion_id: int | None = Field(default=None, foreign_key="suggestion.id")
    description: str
    estimated_hours: Decimal = Field(max_digits=6, decimal_places=2)
    price: Decimal = Field(max_digits=12, decimal_places=2)
    # the milestone that bills this change order; its status is the change order's status
    milestone_id: int = Field(foreign_key="milestone.id")
    created_at: datetime = Field(default_factory=utcnow)


class Deliverable(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    milestone_id: int = Field(foreign_key="milestone.id", index=True)
    filename: str
    content_type: str
    size_bytes: int
    data: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    # watermarked, smaller copy for images; None for other file types.
    # The full file is only served once the milestone is paid.
    preview: bytes | None = Field(default=None, sa_column=Column(LargeBinary, nullable=True))
    uploaded_at: datetime = Field(default_factory=utcnow)


class Reminder(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("invoice_id", "stage"),)

    id: int | None = Field(default=None, primary_key=True)
    invoice_id: int = Field(foreign_key="invoice.id", index=True)
    # days relative to the due date: -3, 0, 3, 7 or 14
    stage: int
    subject: str
    note: str
    sent_at: datetime = Field(default_factory=utcnow)


class AppState(SQLModel, table=True):
    # a single row (id 1) for app-wide settings that change at runtime
    id: int = Field(default=1, primary_key=True)
    # the demo clock: how many days ahead of the real date the app pretends it is
    clock_offset_days: int = 0


class WebhookEvent(SQLModel, table=True):
    id: str = Field(primary_key=True)
    event_type: str
    payload_json: str
    received_at: datetime = Field(default_factory=utcnow)


class AuditEntry(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    contract_id: int | None = Field(default=None, foreign_key="contract.id", index=True)
    # user, client, system, ai or paypal
    actor: str
    action: str
    details_json: str = "{}"
    created_at: datetime = Field(default_factory=utcnow)
