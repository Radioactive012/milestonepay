from decimal import Decimal

import pytest
from sqlmodel import select

from app.billing import approve_change_order, round_to_quarter_hour
from app.milestones import record_revision
from app.models import AuditEntry, ChangeOrder, Contract, Milestone
from app.paypal.client import PayPalError
from tests.conftest import CONTRACT_TEXT


def active_contract(api, session, deposit_pct=0, **form) -> Contract:
    data = {"client_email": "buyer@example.com", "text": CONTRACT_TEXT}
    data.update(form)
    contract_id = api.post("/api/contracts", data=data).json()["id"]
    api.post(f"/api/contracts/{contract_id}/approve", json={"deposit_pct": deposit_pct})
    return session.get(Contract, contract_id)


def test_hourly_rate_defaults_to_40_and_can_be_set(api):
    default = api.post("/api/contracts", data={"client_email": "b@example.com", "text": CONTRACT_TEXT}).json()
    assert default["hourly_rate"] == "40.00"
    custom = api.post(
        "/api/contracts", data={"client_email": "b@example.com", "text": CONTRACT_TEXT, "hourly_rate": "55"}
    ).json()
    assert custom["hourly_rate"] == "55.00"
    updated = api.patch(f"/api/contracts/{custom['id']}", json={"hourly_rate": "60.50"}).json()
    assert updated["hourly_rate"] == "60.50"
    assert api.patch(f"/api/contracts/{custom['id']}", json={"hourly_rate": "0"}).status_code == 422


def test_change_order_becomes_an_invoiced_milestone(api, session, fake_paypal):
    contract = active_contract(api, session)
    order = approve_change_order(
        session, fake_paypal, contract, description="Matching menu design", estimated_hours=Decimal("4"), actor="user"
    )
    assert order.price == Decimal("160.00")
    milestone = session.get(Milestone, order.milestone_id)
    assert milestone.title == "Change order: Matching menu design"
    assert milestone.trigger == "change_order"
    assert milestone.position == 4
    assert milestone.status == "invoiced"
    sent = fake_paypal.invoices["INV2-0001"]
    assert sent["status"] == "SENT"
    assert sent["payload"]["items"][0]["unit_amount"]["value"] == "160.00"

    body = api.get(f"/api/contracts/{contract.id}").json()
    assert body["change_orders"][0]["price"] == "160.00"
    assert body["milestones"][-1]["invoice"]["status"] == "SENT"
    assert "change_order_approved" in [e["action"] for e in body["audit"]]


@pytest.mark.parametrize(
    "raw,expected",
    [("1.1", "1.00"), ("1.13", "1.25"), ("2.6", "2.50"), ("2.63", "2.75"), ("0.2", "0.25"), ("3", "3.00")],
)
def test_round_to_quarter_hour(raw, expected):
    assert round_to_quarter_hour(Decimal(raw)) == Decimal(expected)


def test_change_order_hours_round_to_quarter_hours(api, session, fake_paypal):
    contract = active_contract(api, session, hourly_rate="50")
    order = approve_change_order(
        session, fake_paypal, contract, description="Extra icon", estimated_hours=Decimal("1.1"), actor="user"
    )
    assert order.estimated_hours == Decimal("1.00")
    assert order.price == Decimal("50.00")


@pytest.mark.parametrize(
    "description,hours", [("", Decimal("2")), ("Menu", Decimal("0")), ("Menu", Decimal("-3")), ("Menu", Decimal("500"))]
)
def test_bad_change_orders_are_refused(api, session, fake_paypal, description, hours):
    contract = active_contract(api, session)
    with pytest.raises(ValueError):
        approve_change_order(
            session, fake_paypal, contract, description=description, estimated_hours=hours, actor="user"
        )
    assert session.exec(select(ChangeOrder)).all() == []


def test_change_order_needs_an_approved_contract(api, session, fake_paypal):
    contract_id = api.post("/api/contracts", data={"client_email": "b@example.com", "text": CONTRACT_TEXT}).json()["id"]
    with pytest.raises(ValueError):
        approve_change_order(
            session, fake_paypal, session.get(Contract, contract_id),
            description="Menu", estimated_hours=Decimal("2"), actor="user",
        )


def test_failed_change_order_invoice_can_be_retried(api, session, fake_paypal):
    contract = active_contract(api, session)
    fake_paypal.fail_create = True
    with pytest.raises(PayPalError):
        approve_change_order(
            session, fake_paypal, contract, description="Menu", estimated_hours=Decimal("2"), actor="user"
        )
    order = session.exec(select(ChangeOrder)).one()
    assert session.get(Milestone, order.milestone_id).status == "draft"

    fake_paypal.fail_create = False
    retried = api.post(f"/api/milestones/{order.milestone_id}/invoice").json()
    assert retried["milestones"][-1]["status"] == "invoiced"


def test_revision_counting_flags_rounds_past_the_limit(api, session):
    contract = active_contract(api, session)
    milestone = session.exec(select(Milestone).where(Milestone.contract_id == contract.id)).first()
    milestone.revision_limit = 2
    assert record_revision(session, milestone, "user") is False
    assert record_revision(session, milestone, "user") is False
    assert record_revision(session, milestone, "user") is True
    session.commit()
    assert milestone.revisions_used == 3
    counted = session.exec(select(AuditEntry).where(AuditEntry.action == "revision_counted")).all()
    assert len(counted) == 3
