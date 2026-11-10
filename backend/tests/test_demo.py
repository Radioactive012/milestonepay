from datetime import date, timedelta

from sqlmodel import select

from app.ai.llm import DailyAILimit
from app.models import AppState, AuditEntry, Contract, Invoice, Milestone


def test_load_demo_project_uses_no_ai_and_passes_the_code_checks(api, fake_ai):
    body = api.post("/api/demo/load").json()
    assert fake_ai.calls == []
    assert body["status"] == "draft"
    assert body["client_name"] == "Harbor Lane Bakery"
    assert body["client_email"] == "buyer@example.com"
    assert body["milestone_total"] == "3200.00" and body["stated_total"] == "3200.00"
    assert [r["category"] for r in body["risks"]] == ["vague_acceptance", "unlimited_revisions", "ip_before_payment"]
    # every quote exists word for word, so the code checks drop nothing and warn about nothing
    assert body["warnings"] == []
    assert body["deposit_pct_suggested"] == 30
    logo = body["milestones"][1]
    assert logo["trigger"] == "date"
    assert logo["due_date"] == (date.today() + timedelta(days=21)).isoformat()
    actions = [(e["actor"], e["action"]) for e in body["audit"]]
    assert ("system", "contract_analysed") in actions and ("system", "demo_project_loaded") in actions


def test_demo_project_follows_the_demo_clock(api):
    api.post("/api/demo/clock", json={"offset_days": 10})
    logo = api.post("/api/demo/load").json()["milestones"][1]
    assert logo["due_date"] == (date.today() + timedelta(days=31)).isoformat()


def test_demo_project_can_be_approved_end_to_end(api, fake_paypal):
    contract = api.post("/api/demo/load").json()
    approved = api.post(f"/api/contracts/{contract['id']}/approve", json={"deposit_pct": 30}).json()
    assert approved["milestones"][0]["amount"] == "960.00"
    assert approved["milestones"][0]["status"] == "invoiced"
    assert fake_paypal.invoices["INV2-0001"]["payload"]["primary_recipients"][0]["billing_info"]["email_address"] == (
        "buyer@example.com"
    )


def test_reset_clears_projects_and_clock_but_keeps_ai_usage(api, session, engine, fake_paypal):
    contract = api.post("/api/demo/load").json()
    api.post(f"/api/contracts/{contract['id']}/approve", json={"deposit_pct": 30})
    api.post("/api/demo/clock", json={"offset_days": 20})
    DailyAILimit(engine, 150).take_one()

    body = api.post("/api/demo/reset").json()
    assert body["status"] == "reset"
    assert body["offset_days"] == 0
    assert body["ai_calls_today"] == 1

    session.expire_all()
    for model in (Contract, Milestone, Invoice):
        assert session.exec(select(model)).all() == []
    assert session.get(AppState, 1).ai_calls_count == 1
    assert [e.action for e in session.exec(select(AuditEntry)).all()] == ["demo_clock_set"]
    assert api.get("/api/contracts").json() == []


def test_clock_shows_ai_usage(api, engine):
    DailyAILimit(engine, 150).take_one()
    body = api.get("/api/demo/clock").json()
    assert body["ai_calls_today"] == 1 and body["ai_daily_limit"] == 150


def test_demo_load_and_reset_are_off_outside_demo_mode(api, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "demo_mode", False)
    assert api.post("/api/demo/load").status_code == 404
    assert api.post("/api/demo/reset").status_code == 404
