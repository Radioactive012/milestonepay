import re
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.ai.schemas import ContractAnalysis, Risk

_PUNCTUATION = str.maketrans(
    {"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-"}
)


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.translate(_PUNCTUATION)).strip().lower()


# "two rounds of revisions", "3 revision rounds", "two rounds of edits"
_STATED_REVISIONS = re.compile(
    r"\b(one|two|three|four|five|\d+)\s+(rounds?\s+of\s+)?(revisions?|edits?|changes)\b"
    r"|\b(one|two|three|four|five|\d+)\s+(revision|edit)\s+rounds?\b"
)


def revisions_are_capped(source: str) -> bool:
    """True when the contract states a number of revision rounds and never says unlimited."""
    text = normalise(source)
    return bool(_STATED_REVISIONS.search(text)) and "unlimited" not in text


def quote_in_source(quote: str, source: str) -> bool:
    cleaned = normalise(quote).strip(" .,;:\"'")
    return bool(cleaned) and cleaned in normalise(source)


@dataclass
class CheckedMilestone:
    title: str
    amount: Decimal
    trigger: str
    due_date: date | None
    trigger_description: str
    revision_limit: int | None


@dataclass
class CheckedContract:
    client_name: str | None
    currency: str
    stated_total: Decimal | None
    payment_terms_days: int
    milestones: list[CheckedMilestone]
    risks: list[Risk]
    deposit_pct: int
    deposit_rationale: str
    ambiguities: list[str]
    warnings: list[str] = field(default_factory=list)


def _to_money(value: float) -> Decimal | None:
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None


def _to_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def check_analysis(analysis: ContractAnalysis, source_text: str) -> CheckedContract:
    """Apply code checks to the AI's reading of a contract before anything is saved."""
    warnings: list[str] = []

    currency = analysis.currency.strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        warnings.append(f"Currency '{analysis.currency}' isn't a 3-letter code, so USD is used.")
        currency = "USD"

    risks = [r for r in analysis.risks if quote_in_source(r.clause_quote, source_text)]
    dropped = len(analysis.risks) - len(risks)
    if dropped:
        warnings.append(
            f"{dropped} flagged clause(s) were removed because the quote wasn't found in the contract."
        )
    if revisions_are_capped(source_text) and any(r.category == "unlimited_revisions" for r in risks):
        risks = [r for r in risks if r.category != "unlimited_revisions"]
        warnings.append("An 'unlimited revisions' flag was removed: the contract states a number of revision rounds.")

    milestones: list[CheckedMilestone] = []
    for draft in analysis.milestones:
        amount = _to_money(draft.amount)
        if amount is None or amount <= 0:
            warnings.append(f"Milestone '{draft.title}' has no valid amount and was left out.")
            continue
        due = _to_date(draft.due_date)
        trigger = draft.trigger
        if trigger == "date" and due is None:
            warnings.append(f"Milestone '{draft.title}' has no readable date, so it waits for you to trigger it.")
            trigger = "event"
        if not quote_in_source(draft.source_quote, source_text):
            warnings.append(f"Check milestone '{draft.title}': its source text wasn't found word for word.")
        milestones.append(
            CheckedMilestone(
                title=draft.title.strip(),
                amount=amount,
                trigger=trigger,
                due_date=due if trigger == "date" else None,
                trigger_description=draft.trigger_description.strip(),
                revision_limit=draft.revision_limit,
            )
        )

    stated_total = _to_money(analysis.stated_total) if analysis.stated_total is not None else None
    milestone_sum = sum((m.amount for m in milestones), Decimal("0"))
    if stated_total is not None and milestones and milestone_sum != stated_total:
        warnings.append(
            f"Milestones add up to {currency} {milestone_sum} but the contract total is {currency} {stated_total}."
        )

    terms = analysis.payment_terms_days
    if terms is None or not 0 <= terms <= 120:
        terms = 15

    return CheckedContract(
        client_name=analysis.client_name,
        currency=currency,
        stated_total=stated_total,
        payment_terms_days=terms,
        milestones=milestones,
        risks=risks,
        deposit_pct=analysis.deposit_pct,
        deposit_rationale=analysis.deposit_rationale,
        ambiguities=analysis.ambiguities,
        warnings=warnings,
    )
