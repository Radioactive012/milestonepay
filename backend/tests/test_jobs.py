from datetime import date, timedelta

import pytest
from sqlmodel import select

from app import clock
from app.jobs import reminder_text, run_daily_jobs
from app.models import Invoice, Milestone, Reminder
from tests.conftest import CONTRACT_TEXT


@pytest.fixture
def deposit_invoice(api, session):
    """An active contract whose 30% deposit invoice was just sent (due in 15 days)."""
    contract = api.post("/api/contracts", data={"client_email": "buyer@example.com", "text": CONTRACT_TEXT}).json()
    api.post(f"/api/contracts/{contract['id']}/approve", json={"deposit_pct": 30})
    invoice = session.exec(select(Invoice)).one()
    assert invoice.due_date == date.today() + timedelta(days=15)
    return invoice


def run(session, fake_paypal, today):
    return run_daily_jobs(session, fake_paypal, today)


def test_reminders_follow_the_schedule_and_send_once(session, fake_paypal, deposit_invoice):
    due = deposit_invoice.due_date

    assert run(session, fake_paypal, due - timedelta(days=5))["reminders"] == []

    summary = run(session, fake_paypal, due - timedelta(days=3))
    assert [r["stage"] for r in summary["reminders"]] == [-3]
    assert summary["overdue"] == []
    assert run(session, fake_paypal, due - timedelta(days=3))["reminders"] == []

    summary = run(session, fake_paypal, due)
    assert [r["stage"] for r in summary["reminders"]] == [0]
    assert "Due today" in summary["reminders"][0]["subject"]

    paypal_id, body = fake_paypal.reminders[-1]
    assert paypal_id == deposit_invoice.paypal_invoice_id
    assert body["send_to_invoicer"] is False


def deposit_stages(summary, invoice):
    return [r["stage"] for r in summary["reminders"] if r["number"] == invoice.number]


def test_overdue_jump_sends_one_reminder_for_the_latest_stage(session, fake_paypal, deposit_invoice):
    due = deposit_invoice.due_date
    summary = run(session, fake_paypal, due + timedelta(days=8))
    assert summary["overdue"] == [deposit_invoice.number]
    assert deposit_stages(summary, deposit_invoice) == [7]
    milestone = session.get(Milestone, deposit_invoice.milestone_id)
    assert milestone.status == "overdue"

    summary = run(session, fake_paypal, due + timedelta(days=9))
    assert deposit_stages(summary, deposit_invoice) == []
    assert deposit_invoice.number not in summary["overdue"]

    summary = run(session, fake_paypal, due + timedelta(days=20))
    assert deposit_stages(summary, deposit_invoice) == [14]
    final = next(r for r in summary["reminders"] if r["number"] == deposit_invoice.number)
    assert final["subject"].startswith("Final reminder")
    sent = session.exec(select(Reminder).where(Reminder.invoice_id == deposit_invoice.id)).all()
    assert [r.stage for r in sent] == [7, 14]


def test_paid_invoices_get_no_reminders(api, session, fake_paypal, deposit_invoice):
    api.post(
        "/webhooks/paypal",
        json={"id": "WH-1", "event_type": "INVOICING.INVOICE.PAID",
              "resource": {"invoice": {"id": deposit_invoice.paypal_invoice_id}}},
    )
    summary = run(session, fake_paypal, deposit_invoice.due_date + timedelta(days=30))
    assert summary["reminders"] == [] and summary["overdue"] == []


def test_overdue_invoice_can_still_be_paid(api, session, fake_paypal, deposit_invoice):
    run(session, fake_paypal, deposit_invoice.due_date + timedelta(days=4))
    api.post(
        "/webhooks/paypal",
        json={"id": "WH-2", "event_type": "INVOICING.INVOICE.PAID",
              "resource": {"invoice": {"id": deposit_invoice.paypal_invoice_id}}},
    )
    session.expire_all()
    assert session.get(Milestone, deposit_invoice.milestone_id).status == "paid"


def test_failed_reminder_is_reported_and_retried_next_run(session, fake_paypal, deposit_invoice):
    fake_paypal.fail_remind = True
    summary = run(session, fake_paypal, deposit_invoice.due_date)
    assert summary["reminders"] == [] and "failed" in summary["errors"][0]
    assert session.exec(select(Reminder)).all() == []

    fake_paypal.fail_remind = False
    summary = run(session, fake_paypal, deposit_invoice.due_date)
    assert [r["stage"] for r in summary["reminders"]] == [0]


def test_dated_milestone_is_invoiced_a_week_before_its_due_date(session, fake_paypal, deposit_invoice):
    logo = session.exec(select(Milestone).where(Milestone.title == "Final logo")).one()
    assert logo.status == "scheduled" and logo.due_date == date(2026, 12, 1)

    assert run(session, fake_paypal, date(2026, 11, 23))["invoiced"] == []
    summary = run(session, fake_paypal, date(2026, 11, 24))
    assert len(summary["invoiced"]) == 1
    session.refresh(logo)
    assert logo.status == "invoiced"
    invoice = session.exec(select(Invoice).where(Invoice.milestone_id == logo.id)).one()
    assert invoice.due_date == date(2026, 12, 1)
    assert run(session, fake_paypal, date(2026, 11, 25))["invoiced"] == []


def test_reminder_text_by_stage(deposit_invoice):
    assert "is due on" in reminder_text(-3, deposit_invoice)[1]
    assert "due today" in reminder_text(0, deposit_invoice)[1]
    assert "5 days overdue" in reminder_text(5, deposit_invoice)[1]
    assert reminder_text(15, deposit_invoice)[0].startswith("Final reminder")
    assert "USD 960.00" in reminder_text(0, deposit_invoice)[1]


def test_demo_clock_routes(api, session):
    assert api.get("/api/demo/clock").json()["offset_days"] == 0
    body = api.post("/api/demo/clock", json={"offset_days": 7}).json()
    assert body["offset_days"] == 7
    assert body["today"] == (date.today() + timedelta(days=7)).isoformat()
    assert clock.today(session) == date.today() + timedelta(days=7)
    assert api.post("/api/demo/clock", json={"offset_days": -1}).status_code == 422
    assert api.post("/api/demo/clock", json={"offset_days": 0}).json()["offset_days"] == 0


def test_demo_run_jobs_uses_the_demo_clock(api, fake_paypal, deposit_invoice):
    api.post("/api/demo/clock", json={"offset_days": 23})
    summary = api.post("/api/demo/run-jobs").json()
    assert summary["today"] == (date.today() + timedelta(days=23)).isoformat()
    assert summary["overdue"] == [deposit_invoice.number]
    assert [r["stage"] for r in summary["reminders"] if r["number"] == deposit_invoice.number] == [7]

    contract = api.get("/api/contracts/1").json()
    assert contract["milestones"][0]["status"] == "overdue"
    assert contract["milestones"][0]["invoice"]["reminders"][0]["stage"] == 7


def test_invoices_use_the_demo_clock_for_due_dates(api, session, fake_paypal):
    api.post("/api/demo/clock", json={"offset_days": 10})
    contract = api.post("/api/contracts", data={"client_email": "buyer@example.com", "text": CONTRACT_TEXT}).json()
    api.post(f"/api/contracts/{contract['id']}/approve", json={"deposit_pct": 25})
    invoice = session.exec(select(Invoice)).one()
    assert invoice.due_date == date.today() + timedelta(days=10 + 15)


def test_demo_routes_can_be_turned_off(api, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "demo_mode", False)
    assert api.get("/api/demo/clock").status_code == 404
    assert api.post("/api/demo/run-jobs").status_code == 404
