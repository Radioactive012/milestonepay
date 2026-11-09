from decimal import ROUND_HALF_UP, Decimal

import pytest

from app.ai.guardrails import check_analysis, quote_in_source
from app.milestones import apply_deposit
from tests.conftest import CONTRACT_TEXT, sample_analysis


def test_quote_check_ignores_whitespace_case_and_curly_quotes():
    source = "The Client may request\n  unlimited   revisions. It's “final”."
    assert quote_in_source("the client may request unlimited revisions", source)
    assert quote_in_source('It’s "final".', source)
    assert not quote_in_source("The client may request three revisions", source)
    assert not quote_in_source("  ", source)


def test_made_up_risk_is_dropped_with_a_warning():
    checked = check_analysis(sample_analysis(), CONTRACT_TEXT)
    assert [r.category for r in checked.risks] == ["vague_acceptance"]
    assert any("removed because the quote wasn't found" in w for w in checked.warnings)


def test_currency_is_normalised_and_amounts_are_decimals():
    checked = check_analysis(sample_analysis(), CONTRACT_TEXT)
    assert checked.currency == "USD"
    assert [m.amount for m in checked.milestones] == [Decimal("800.00"), Decimal("1400.00"), Decimal("1000.00")]
    assert checked.milestones[1].due_date.isoformat() == "2026-12-01"


def test_total_mismatch_is_flagged():
    checked = check_analysis(sample_analysis(stated_total=3500), CONTRACT_TEXT)
    assert any("add up to USD 3200.00" in w for w in checked.warnings)


def test_zero_amount_milestone_is_left_out():
    analysis = sample_analysis()
    analysis.milestones[0].amount = 0
    checked = check_analysis(analysis, CONTRACT_TEXT)
    assert [m.title for m in checked.milestones] == ["Final logo", "Brand kit"]


def test_date_trigger_without_a_date_becomes_event():
    analysis = sample_analysis()
    analysis.milestones[1].due_date = "next month"
    checked = check_analysis(analysis, CONTRACT_TEXT)
    assert checked.milestones[1].trigger == "event"
    assert checked.milestones[1].due_date is None


@pytest.mark.parametrize("pct", [0, 25, 30, 50])
def test_deposit_split_keeps_the_total(pct):
    amounts = [Decimal("800.00"), Decimal("1400.00"), Decimal("1000.01")]
    deposit, reduced = apply_deposit(amounts, pct)
    assert deposit + sum(reduced) == sum(amounts)
    assert deposit == (sum(amounts) * pct / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def test_deposit_above_half_is_refused():
    with pytest.raises(ValueError):
        apply_deposit([Decimal("100")], 60)
