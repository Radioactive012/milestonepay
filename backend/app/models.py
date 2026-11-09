import secrets
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Contract(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    client_name: str
    client_email: str
    currency: str = "USD"
    stated_total: Decimal | None = Field(default=None, max_digits=12, decimal_places=2)
    payment_terms_days: int = 15
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
    # date, event, or approval (the deposit)
    trigger: str
    trigger_description: str = ""
    due_date: date | None = None
    revision_limit: int | None = None
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
