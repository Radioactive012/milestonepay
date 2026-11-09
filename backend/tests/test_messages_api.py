from decimal import Decimal

import pytest
from sqlmodel import select

from app.ai.messages import MessageAIError, MessageAnalysis, MilestoneSignal, OutOfScope, RevisionRequest, get_message_ai
from app.main import app
from app.models import AuditEntry, ChangeOrder, Contract, Milestone
from tests.conftest import CONTRACT_TEXT

MESSAGE = "Sketches approved! Could you also add a matching menu design?"
CLAUSE = "Brand kit: $1,000, due on delivery of the brand kit."


def demo_analysis(**overrides) -> MessageAnalysis:
    data = dict(
        milestone_signals=[MilestoneSignal(milestone_title="Sketches", quote="Sketches approved", confidence=0.95)],
        out_of_scope=[
            OutOfScope(
                request_quote="add a matching menu design",
                contract_clause_quote=CLAUSE,
                reason="Menus are not in the scope",
                estimated_hours=4,
                confidence=0.9,
            )
        ],
        revision_requests=[],
    )
    data.update(overrides)
    return MessageAnalysis(**data)


class FakeMessageAI:
    def __init__(self, analysis=None):
        self.analysis = analysis or demo_analysis()
        self.failures = 0  # how many calls fail before one succeeds
        self.calls = 0

    def analyse(self, *, message, contract_text, milestones):
        self.calls += 1
        if self.calls <= self.failures:
            raise MessageAIError("Couldn't reach the AI service. Check the internet connection.")
        return self.analysis


@pytest.fixture
def message_ai(api):
    fake = FakeMessageAI()
    app.dependency_overrides[get_message_ai] = lambda: fake
    return fake


@pytest.fixture
def contract(api, session):
    contract_id = api.post("/api/contracts", data={"client_email": "b@example.com", "text": CONTRACT_TEXT}).json()["id"]
    api.post(f"/api/contracts/{contract_id}/approve", json={"deposit_pct": 0})
    return session.get(Contract, contract_id)


def post_message(api, contract, body=MESSAGE):
    return api.post("/api/messages", json={"contract_id": contract.id, "body": body})


def test_message_becomes_two_pending_suggestions(api, message_ai, contract):
    response = post_message(api, contract)
    assert response.status_code == 201
    body = response.json()
    assert [s["type"] for s in body["suggestions"]] == ["milestone_reached", "scope_creep"]
    scope = body["suggestions"][1]
    assert scope["payload"]["estimated_hours"] == "4.00"
    assert scope["payload"]["price"] == "160.00"  # hours x the contract's hourly rate, set by code
    assert scope["possible"] is False
    inbox = api.get("/api/suggestions?status=pending").json()
    assert len(inbox) == 2
    assert inbox[0]["message_body"] == MESSAGE


def test_made_up_quotes_never_become_suggestions(api, message_ai, contract):
    message_ai.analysis = demo_analysis(
        milestone_signals=[MilestoneSignal(milestone_title="Sketches", quote="Everything is paid", confidence=0.9)],
        out_of_scope=[],
    )
    body = post_message(api, contract).json()
    assert body["suggestions"] == []
    assert body["dropped"]


def test_message_needs_an_approved_contract(api, message_ai):
    draft = api.post("/api/contracts", data={"client_email": "b@example.com", "text": CONTRACT_TEXT}).json()
    assert api.post("/api/messages", json={"contract_id": draft["id"], "body": MESSAGE}).status_code == 409


def test_ai_failure_retries_once_then_gives_up(api, message_ai, contract):
    message_ai.failures = 1
    assert post_message(api, contract).status_code == 201
    assert message_ai.calls == 2

    message_ai.calls, message_ai.failures = 0, 5
    response = post_message(api, contract)
    assert response.status_code == 502
    assert message_ai.calls == 2
    assert len(api.get(f"/api/messages?contract_id={contract.id}").json()) == 1


def test_approving_milestone_reached_sends_the_invoice(api, message_ai, contract, fake_paypal):
    suggestion = post_message(api, contract).json()["suggestions"][0]
    result = api.post(f"/api/suggestions/{suggestion['id']}/approve")
    assert result.status_code == 200
    sketches = result.json()["contract"]["milestones"][0]
    assert sketches["status"] == "invoiced"
    assert sketches["invoice"]["amount"] == "800.00"
    assert result.json()["suggestion"]["status"] == "approved"
    assert api.post(f"/api/suggestions/{suggestion['id']}/approve").status_code == 409


def test_approving_scope_creep_creates_and_invoices_a_change_order(api, message_ai, contract, session):
    suggestion = post_message(api, contract).json()["suggestions"][1]
    result = api.post(f"/api/suggestions/{suggestion['id']}/approve")
    assert result.status_code == 200
    order = result.json()["contract"]["change_orders"][0]
    assert order["price"] == "160.00"
    assert result.json()["contract"]["milestones"][-1]["invoice"]["status"] == "SENT"


def test_freelancer_can_edit_the_hours_before_approving(api, message_ai, contract):
    suggestion = post_message(api, contract).json()["suggestions"][1]
    result = api.post(f"/api/suggestions/{suggestion['id']}/approve", json={"hours": "2.5", "description": "Menu"})
    order = result.json()["contract"]["change_orders"][0]
    assert order["estimated_hours"] == "2.50"
    assert order["price"] == "100.00"
    assert order["description"] == "Menu"
    assert api.post(f"/api/suggestions/{suggestion['id']}/approve", json={"hours": "0"}).status_code in (409, 422)


def test_change_order_is_kept_when_paypal_fails(api, message_ai, contract, session, fake_paypal):
    suggestion = post_message(api, contract).json()["suggestions"][1]
    fake_paypal.fail_create = True
    response = api.post(f"/api/suggestions/{suggestion['id']}/approve")
    assert response.status_code == 502
    assert "Send invoice" in response.json()["detail"]
    order = session.exec(select(ChangeOrder)).one()
    assert api.get("/api/suggestions?status=approved").json()[0]["id"] == suggestion["id"]

    fake_paypal.fail_create = False
    retried = api.post(f"/api/milestones/{order.milestone_id}/invoice")
    assert retried.json()["milestones"][-1]["status"] == "invoiced"
    assert len(session.exec(select(ChangeOrder)).all()) == 1  # no duplicate change order


def test_dismissing_changes_nothing_else(api, message_ai, contract, session):
    suggestion = post_message(api, contract).json()["suggestions"][1]
    assert api.post(f"/api/suggestions/{suggestion['id']}/dismiss").json()["status"] == "dismissed"
    assert session.exec(select(ChangeOrder)).all() == []
    assert api.post(f"/api/suggestions/{suggestion['id']}/dismiss").status_code == 409
    actions = [e.action for e in session.exec(select(AuditEntry)).all()]
    assert "suggestion_dismissed" in actions and "message_analysed" in actions


def test_low_confidence_suggestions_cannot_be_approved(api, message_ai, contract):
    message_ai.analysis = demo_analysis(
        milestone_signals=[MilestoneSignal(milestone_title="Sketches", quote="Sketches approved", confidence=0.4)],
        out_of_scope=[],
    )
    suggestion = post_message(api, contract).json()["suggestions"][0]
    assert suggestion["possible"] is True
    assert api.post(f"/api/suggestions/{suggestion['id']}/approve").status_code == 409


def test_approving_a_revision_counts_it(api, message_ai, contract, session):
    sketches = session.exec(select(Milestone).where(Milestone.contract_id == contract.id)).first()
    sketches.revision_limit = 1
    session.add(sketches)
    session.commit()
    message_ai.analysis = demo_analysis(
        milestone_signals=[],
        out_of_scope=[],
        revision_requests=[RevisionRequest(milestone_title="Sketches", quote="tweak the font", confidence=0.9)],
    )
    message = "Please tweak the font on concept two"
    suggestion = post_message(api, contract, message).json()["suggestions"][0]
    assert suggestion["payload"]["over_limit"] is False
    api.post(f"/api/suggestions/{suggestion['id']}/approve")
    session.refresh(sketches)
    assert sketches.revisions_used == 1

    second = post_message(api, contract, message).json()["suggestions"][0]
    assert second["payload"]["over_limit"] is True


def test_no_second_invoice_suggestion_for_a_milestone_already_billed(api, message_ai, contract):
    first = post_message(api, contract).json()["suggestions"][0]
    again = post_message(api, contract).json()
    assert [s["type"] for s in again["suggestions"]] == ["scope_creep"]
    assert any("already has a pending suggestion" in d for d in again["dropped"])
    api.post(f"/api/suggestions/{first['id']}/approve")
    after = post_message(api, contract).json()
    assert any("already invoiced" in d for d in after["dropped"])


def test_message_thread_lists_messages_with_tags(api, message_ai, contract):
    post_message(api, contract)
    thread = api.get(f"/api/messages?contract_id={contract.id}").json()
    assert thread[0]["body"] == MESSAGE
    assert {t["type"] for t in thread[0]["tags"]} == {"milestone_reached", "scope_creep"}


def test_inbox_lists_newest_message_first_and_keeps_order_within_a_message(api, message_ai, contract):
    post_message(api, contract)
    message_ai.analysis = demo_analysis(milestone_signals=[])
    post_message(api, contract, "Please also add a matching menu design for us")
    types = [s["type"] for s in api.get("/api/suggestions").json()]
    assert types == ["scope_creep", "milestone_reached", "scope_creep"]
