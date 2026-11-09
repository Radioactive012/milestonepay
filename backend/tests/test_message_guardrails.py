from decimal import Decimal

from app.ai.messages import (
    MessageAnalysis,
    MilestoneSignal,
    OutOfScope,
    RevisionRequest,
    check_message_analysis,
)

CONTRACT = "Scope: sketches, final logo, brand kit. Menus and packaging are outside this contract."
MESSAGE = "Sketches approved! Could you also add a matching menu design?"
TITLES = ["Sketches", "Final logo", "Brand kit"]


def analysis(**kw):
    base = dict(
        milestone_signals=[MilestoneSignal(milestone_title="sketches", quote="Sketches approved", confidence=0.95)],
        out_of_scope=[
            OutOfScope(
                request_quote="add a matching menu design",
                contract_clause_quote="Menus and packaging are outside this contract",
                reason="Menus are excluded",
                estimated_hours=4,
                confidence=0.9,
            )
        ],
        revision_requests=[],
    )
    base.update(kw)
    return MessageAnalysis(**base)


def test_valid_analysis_is_kept_and_priced_by_code():
    checked = check_message_analysis(analysis(), MESSAGE, CONTRACT, TITLES, Decimal("40"))
    assert [s.milestone_title for s in checked.milestone_signals] == ["Sketches"]
    assert checked.out_of_scope[0].price == Decimal("160.00")
    assert not checked.out_of_scope[0].possible
    assert checked.dropped == []


def test_made_up_quotes_are_dropped():
    bad = analysis(
        milestone_signals=[MilestoneSignal(milestone_title="Final logo", quote="Final logo approved", confidence=0.9)],
        out_of_scope=[
            OutOfScope(
                request_quote="add a matching menu design",
                contract_clause_quote="Menus cost extra",
                reason="x",
                estimated_hours=2,
                confidence=0.9,
            )
        ],
    )
    checked = check_message_analysis(bad, MESSAGE, CONTRACT, TITLES, Decimal("40"))
    assert checked.milestone_signals == [] and checked.out_of_scope == []
    assert len(checked.dropped) == 2


def test_unknown_milestone_is_dropped():
    bad = analysis(revision_requests=[RevisionRequest(milestone_title="Website", quote="Sketches approved", confidence=0.9)])
    checked = check_message_analysis(bad, MESSAGE, CONTRACT, TITLES, Decimal("40"))
    assert checked.revision_requests == []
    assert any("Unknown milestone" in d for d in checked.dropped)


def test_low_confidence_is_marked_possible():
    low = analysis()
    low.out_of_scope[0].confidence = 0.5
    checked = check_message_analysis(low, MESSAGE, CONTRACT, TITLES, Decimal("40"))
    assert checked.out_of_scope[0].possible


def test_hours_round_to_quarter_hours_and_never_to_zero():
    for raw, expected in [("1.1", "1.00"), ("2.63", "2.75"), ("0.05", "0.25")]:
        item = analysis()
        item.out_of_scope[0].estimated_hours = float(raw)
        checked = check_message_analysis(item, MESSAGE, CONTRACT, TITLES, Decimal("40"))
        assert checked.out_of_scope[0].estimated_hours == Decimal(expected)
