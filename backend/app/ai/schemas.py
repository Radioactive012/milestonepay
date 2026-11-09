from typing import Literal

from pydantic import BaseModel, Field

RiskCategory = Literal[
    "vague_acceptance",
    "unlimited_revisions",
    "ip_before_payment",
    "long_payment_terms",
    "no_kill_fee",
    "no_late_fee",
    "undefined_scope",
    "other",
]


class MilestoneDraft(BaseModel):
    title: str
    amount: float = Field(description="Amount in the contract currency")
    trigger: Literal["date", "event"] = Field(
        description="date if payment is due on a calendar date, event if it is due when something happens"
    )
    due_date: str | None = Field(description="ISO date (YYYY-MM-DD) for date triggers, otherwise null")
    trigger_description: str = Field(description="What has to happen before this milestone is billed")
    revision_limit: int | None = Field(description="Revision rounds included, or null if not stated")
    source_quote: str = Field(description="The exact contract text this milestone comes from")


class Risk(BaseModel):
    clause_quote: str = Field(description="The risky clause, copied exactly from the contract")
    category: RiskCategory
    severity: Literal["low", "medium", "high"]
    why_it_matters: str
    suggested_rewrite: str


class ContractAnalysis(BaseModel):
    transcription: str = Field(
        description="Full contract text when it came as an image or PDF; empty string when it came as plain text"
    )
    client_name: str | None
    currency: str = Field(description="ISO 4217 code, for example USD, EUR or INR")
    stated_total: float | None = Field(description="Total contract value if the contract states one")
    payment_terms_days: int | None = Field(description="Days the client has to pay each invoice, if stated")
    milestones: list[MilestoneDraft]
    risks: list[Risk]
    deposit_pct: Literal[0, 25, 30, 50]
    deposit_rationale: str
    ambiguities: list[str] = Field(description="Things the freelancer should clarify with the client")
