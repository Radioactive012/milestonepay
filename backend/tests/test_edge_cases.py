"""Edge cases found during the full test pass: double clicks, refunds, out-of-order PayPal events."""
import threading
import time
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.ai.contract import get_contract_ai
from app.ai.llm import DailyAILimit, get_ai_limit
from app.billing import approve_change_order, invoice_milestone, sync_from_paypal
from app.db import get_session, init_db, make_engine
from app.main import app
from app.milestones import apply_deposit
from app.models import ChangeOrder, Contract, Invoice, Milestone, Suggestion
from app.paypal.client import PayPalError, get_paypal_client
from tests.conftest import CONTRACT_TEXT, TEST_DATABASE_URL, FakeAI, FakePayPal
from tests.test_portal import active_contract, pay, png_bytes, upload


class SlowPayPal(FakePayPal):
    """PayPal that takes a moment to create an invoice, so two clicks overlap like they do for real."""

    def __init__(self):
        super().__init__()
        self.lock = threading.Lock()

    def request(self, method, path, json=None, **kwargs):
        if method == "POST" and path == "/v2/invoicing/invoices":
            time.sleep(0.2)
        with self.lock:
            return super().request(method, path, json=json, **kwargs)


@pytest.fixture
def file_engine(tmp_path, request):
    if TEST_DATABASE_URL:
        return request.getfixturevalue("engine")
    # a real file, so separate threads get separate connections like the live app
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    init_db(engine)
    return engine


@pytest.fixture
def slow_paypal():
    return SlowPayPal()


@pytest.fixture
def threaded_api(file_engine, slow_paypal):
    def override_session():
        with Session(file_engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_paypal_client] = lambda: slow_paypal
    app.dependency_overrides[get_contract_ai] = lambda: FakeAI()
    app.dependency_overrides[get_ai_limit] = lambda: DailyAILimit(file_engine, 150)
    yield TestClient(app)
    app.dependency_overrides.clear()


def at_once(*calls):
    """Run the calls in parallel threads, like two quick clicks, and return their results."""
    results = [None] * len(calls)

    def run(i, call):
        try:
            results[i] = call()
        except Exception as error:  # noqa: BLE001  the test checks what came back
            results[i] = error

    threads = [threading.Thread(target=run, args=(i, c)) for i, c in enumerate(calls)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def make_suggestion(engine, contract_id) -> int:
    with Session(engine) as session:
        suggestion = Suggestion(contract_id=contract_id, type="scope_creep")
        session.add(suggestion)
        session.commit()
        return suggestion.id


def created_invoices(paypal) -> int:
    return sum(1 for method, path, _ in paypal.calls if method == "POST" and path == "/v2/invoicing/invoices")


# Double clicks


def test_double_click_on_approve_sends_one_deposit_invoice(threaded_api, slow_paypal, file_engine):
    contract = threaded_api.post("/api/contracts", data={"client_email": "b@example.com", "text": CONTRACT_TEXT}).json()
    url = f"/api/contracts/{contract['id']}/approve"
    first, second = at_once(
        lambda: TestClient(app).post(url, json={"deposit_pct": 30}),
        lambda: TestClient(app).post(url, json={"deposit_pct": 30}),
    )
    assert sorted([first.status_code, second.status_code]) == [200, 409]
    assert created_invoices(slow_paypal) == 1
    with Session(file_engine) as session:
        deposits = session.exec(select(Milestone).where(Milestone.is_deposit)).all()
        assert len(deposits) == 1


def test_double_click_on_send_invoice_sends_one_invoice(threaded_api, slow_paypal, file_engine):
    contract = active_contract(threaded_api)
    sketches = contract["milestones"][1]
    url = f"/api/milestones/{sketches['id']}/invoice"
    first, second = at_once(lambda: TestClient(app).post(url), lambda: TestClient(app).post(url))
    # the second click either gets the same invoice back or "already invoiced", never an error
    assert {first.status_code, second.status_code} <= {200, 409} and 200 in (first.status_code, second.status_code)
    assert created_invoices(slow_paypal) == 2  # the deposit, then this milestone once
    with Session(file_engine) as session:
        assert len(session.exec(select(Invoice).where(Invoice.milestone_id == sketches["id"])).all()) == 1


def test_client_double_click_on_approve_sends_one_invoice(threaded_api, slow_paypal, file_engine):
    contract = active_contract(threaded_api)
    sketches = contract["milestones"][1]
    url = f"/api/portal/{contract['portal_token']}/milestones/{sketches['id']}/approve"
    at_once(lambda: TestClient(app).post(url), lambda: TestClient(app).post(url))
    with Session(file_engine) as session:
        assert len(session.exec(select(Invoice).where(Invoice.milestone_id == sketches["id"])).all()) == 1


def test_same_change_order_approved_twice_at_once_is_made_once(threaded_api, slow_paypal, file_engine):
    contract = active_contract(threaded_api)
    suggestion_id = make_suggestion(file_engine, contract["id"])

    def approve():
        with Session(file_engine) as session:
            return approve_change_order(
                session, slow_paypal, session.get(Contract, contract["id"]),
                description="Menu design", estimated_hours=Decimal("3"), actor="user", suggestion_id=suggestion_id,
            ).id

    first, second = at_once(approve, approve)
    assert first == second
    with Session(file_engine) as session:
        assert len(session.exec(select(ChangeOrder)).all()) == 1


def test_change_order_for_an_approved_suggestion_is_not_made_again(api, session, engine, fake_paypal):
    contract = active_contract(api)
    suggestion_id = make_suggestion(engine, contract["id"])
    c = session.get(Contract, contract["id"])
    first = approve_change_order(session, fake_paypal, c, description="Menu", estimated_hours=Decimal("2"),
                                 actor="user", suggestion_id=suggestion_id)
    second = approve_change_order(session, fake_paypal, c, description="Menu", estimated_hours=Decimal("2"),
                                  actor="user", suggestion_id=suggestion_id)
    assert first.id == second.id
    assert len(session.exec(select(ChangeOrder)).all()) == 1


# Retrying after PayPal sent the invoice but our side didn't hear back


def test_retry_after_lost_send_answer_does_not_send_twice(api, session, fake_paypal):
    contract = active_contract(api, deposit_pct=0)
    sketches = session.get(Milestone, contract["milestones"][0]["id"])
    original = fake_paypal.request
    state = {"fail_get_once": True}

    def flaky(method, path, json=None, **kwargs):
        result = original(method, path, json=json, **kwargs)
        if method == "GET" and state["fail_get_once"]:
            state["fail_get_once"] = False
            raise PayPalError(503, "timed out")
        return result

    fake_paypal.request = flaky
    with pytest.raises(PayPalError):
        invoice_milestone(session, fake_paypal, sketches, "user")
    session.rollback()
    invoice = invoice_milestone(session, fake_paypal, sketches, "user")
    assert invoice.status == "SENT"
    sends = [p for m, p, _ in fake_paypal.calls if p.endswith("/send")]
    assert len(sends) == 1


# Refunds, cancellations and events in a strange order


def event(api, event_id, event_type, paypal_id):
    return api.post(
        "/webhooks/paypal",
        json={"id": event_id, "event_type": event_type, "resource": {"invoice": {"id": paypal_id}}},
    )


def test_cancelled_invoice_cancels_the_milestone(api):
    contract = active_contract(api)
    deposit = contract["milestones"][0]
    assert event(api, "E1", "INVOICING.INVOICE.CANCELLED", deposit["invoice"]["paypal_invoice_id"]).json() == {"status": "ok"}
    after = api.get(f"/api/contracts/{contract['id']}").json()["milestones"][0]
    assert after["status"] == "cancelled"
    assert after["invoice"]["status"] == "CANCELLED"


def test_refund_locks_the_files_again(api):
    contract = active_contract(api)
    deposit = contract["milestones"][0]
    file_id = upload(api, deposit["id"]).json()["id"]
    token = contract["portal_token"]
    pay(api, "E1", deposit["invoice"]["paypal_invoice_id"])
    assert api.get(f"/api/portal/{token}/files/{file_id}").status_code == 200

    event(api, "E2", "INVOICING.INVOICE.REFUNDED", deposit["invoice"]["paypal_invoice_id"])
    assert api.get(f"/api/portal/{token}/files/{file_id}").status_code == 402
    portal = api.get(f"/api/portal/{token}").json()
    assert portal["milestones"][0]["files"][0]["locked"] is True
    assert portal["milestones"][0]["invoice"]["status"] == "REFUNDED"
    assert portal["paid"] == "0.00"


def test_late_paid_event_after_refund_is_ignored(api):
    contract = active_contract(api)
    paypal_id = contract["milestones"][0]["invoice"]["paypal_invoice_id"]
    pay(api, "E1", paypal_id)
    event(api, "E2", "INVOICING.INVOICE.REFUNDED", paypal_id)
    pay(api, "E3", paypal_id)  # PayPal delivered an older event late
    invoice = api.get(f"/api/contracts/{contract['id']}").json()["milestones"][0]["invoice"]
    assert invoice["status"] == "REFUNDED"


def test_cancel_event_for_a_paid_invoice_is_ignored(api):
    contract = active_contract(api)
    paypal_id = contract["milestones"][0]["invoice"]["paypal_invoice_id"]
    pay(api, "E1", paypal_id)
    event(api, "E2", "INVOICING.INVOICE.CANCELLED", paypal_id)
    after = api.get(f"/api/contracts/{contract['id']}").json()["milestones"][0]
    assert after["status"] == "paid"
    assert after["invoice"]["status"] == "PAID"


def test_overdue_invoice_can_still_be_paid(api, session):
    contract = active_contract(api)
    deposit = session.get(Milestone, contract["milestones"][0]["id"])
    api.post("/api/demo/clock", json={"offset_days": 40})
    api.post("/api/demo/run-jobs")
    session.refresh(deposit)
    assert deposit.status == "overdue"
    pay(api, "E1", contract["milestones"][0]["invoice"]["paypal_invoice_id"])
    session.refresh(deposit)
    assert deposit.status == "paid"


@pytest.mark.parametrize(
    "paypal_status, invoice_status, milestone_status",
    [
        ("PAID", "PAID", "paid"),
        ("MARKED_AS_PAID", "PAID", "paid"),
        ("CANCELLED", "CANCELLED", "cancelled"),
        ("MARKED_AS_REFUNDED", "REFUNDED", "invoiced"),
        ("SENT", "SENT", "invoiced"),
        ("UNPAID", "SENT", "invoiced"),
    ],
)
def test_check_payment_follows_paypal(api, session, fake_paypal, paypal_status, invoice_status, milestone_status):
    contract = active_contract(api)
    invoice = session.get(Invoice, contract["milestones"][0]["invoice"]["id"])
    fake_paypal.invoices[invoice.paypal_invoice_id]["status"] = paypal_status
    assert api.post(f"/api/invoices/{invoice.id}/refresh").status_code == 200
    after = api.get(f"/api/contracts/{contract['id']}").json()["milestones"][0]
    assert after["invoice"]["status"] == invoice_status
    assert after["status"] == milestone_status


def test_check_payment_error_says_why(api, session, fake_paypal):
    contract = active_contract(api)
    fake_paypal.request = lambda *a, **k: (_ for _ in ()).throw(PayPalError(401, '{"error_description":"Bad keys"}'))
    response = api.post(f"/api/invoices/{contract['milestones'][0]['invoice']['id']}/refresh")
    assert response.status_code == 502
    assert "Bad keys" in response.json()["detail"]


# Editing and money rules


def test_milestones_cant_be_edited_after_approval(api, fake_paypal):
    fake_paypal.fail_create = True
    contract = api.post("/api/contracts", data={"client_email": "b@example.com", "text": CONTRACT_TEXT}).json()
    approved = api.post(f"/api/contracts/{contract['id']}/approve", json={"deposit_pct": 30})
    assert approved.status_code == 502  # PayPal down, so the deposit stays a draft
    deposit = api.get(f"/api/contracts/{contract['id']}").json()["milestones"][0]
    assert deposit["is_deposit"] and deposit["status"] == "draft"
    response = api.patch(f"/api/milestones/{deposit['id']}", json={"amount": "1.00", "trigger": "date"})
    assert response.status_code == 409


def test_deposit_split_never_leaves_an_empty_milestone():
    deposit, reduced = apply_deposit([Decimal("100.00"), Decimal("0.01")], 50)
    assert deposit + sum(reduced) == Decimal("100.01")
    assert all(amount > 0 for amount in reduced)


@pytest.mark.parametrize("seed", range(30))
def test_deposit_split_random_amounts(seed):
    import random

    rng = random.Random(seed)
    amounts = [Decimal(rng.randint(100, 500_000)) / 100 for _ in range(rng.randint(1, 12))]
    pct = rng.choice([0, 10, 25, 30, 33, 50])
    deposit, reduced = apply_deposit(amounts, pct)
    assert deposit + sum(reduced) == sum(amounts)
    assert all(a > 0 and a == a.quantize(Decimal("0.01")) for a in reduced)


@pytest.mark.parametrize("rate", ["NaN", "Infinity", "-5", "0", "abc"])
def test_bad_hourly_rate_on_new_contract_is_refused(api, rate):
    response = api.post(
        "/api/contracts", data={"client_email": "b@example.com", "text": CONTRACT_TEXT, "hourly_rate": rate}
    )
    assert response.status_code == 422


def test_preview_of_a_non_image_says_so(api):
    contract = active_contract(api)
    file_id = upload(api, contract["milestones"][0]["id"], "brief.pdf", b"%PDF-1.4", "application/pdf").json()["id"]
    response = api.get(f"/api/portal/{contract['portal_token']}/files/{file_id}/preview")
    assert response.status_code == 404


def test_upload_to_a_cancelled_milestone_is_refused(api):
    contract = active_contract(api)
    deposit = contract["milestones"][0]
    event(api, "E1", "INVOICING.INVOICE.CANCELLED", deposit["invoice"]["paypal_invoice_id"])
    assert upload(api, deposit["id"]).status_code == 409


def test_freelancer_can_download_own_file_any_time(api):
    contract = active_contract(api)
    data = png_bytes()
    file_id = upload(api, contract["milestones"][1]["id"], data=data).json()["id"]
    response = api.get(f"/api/files/{file_id}")
    assert response.status_code == 200 and response.content == data
    assert api.get("/api/files/9999").status_code == 404


# Hosting: Neon and Render give database addresses in a few spellings


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://user:pw@ep-cool-1.eu-central-1.aws.neon.tech/neondb?sslmode=require",
        "postgres://user:pw@ep-cool-1.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require",
    ],
)
def test_neon_address_uses_psycopg_and_keeps_ssl(url):
    engine = make_engine(url)  # makes no connection yet
    assert engine.url.drivername == "postgresql+psycopg"
    assert engine.url.query["sslmode"] == "require"
    assert engine.url.host.endswith("neon.tech") and engine.url.database == "neondb"


# Status rules and the daily jobs


def test_every_status_change_follows_the_rules(session):
    from app.milestones import TRANSITIONS, InvalidTransition, move

    statuses = list(TRANSITIONS)
    contract = Contract(client_name="C", client_email="b@example.com", currency="USD", raw_text="x")
    session.add(contract)
    session.commit()
    for old in statuses:
        for new in statuses:
            milestone = Milestone(contract_id=contract.id, position=1, title="M", amount=Decimal("10"), trigger="event", status=old)
            session.add(milestone)
            session.flush()
            if new in TRANSITIONS[old]:
                move(session, milestone, new, "user")
                assert milestone.status == new
            else:
                with pytest.raises(InvalidTransition):
                    move(session, milestone, new, "user")
                assert milestone.status == old
    assert TRANSITIONS["paid"] == set() and TRANSITIONS["cancelled"] == set()


def test_rate_change_after_a_change_order_keeps_its_invoice(api, session, fake_paypal):
    contract = active_contract(api)
    order = approve_change_order(
        session, fake_paypal, session.get(Contract, contract["id"]),
        description="Menu", estimated_hours=Decimal("2.13"), actor="user",
    )
    assert order.estimated_hours == Decimal("2.25") and order.price == Decimal("90.00")
    api.patch(f"/api/contracts/{contract['id']}", json={"hourly_rate": "100"})
    invoice = session.exec(select(Invoice).where(Invoice.milestone_id == order.milestone_id)).one()
    session.refresh(invoice)
    assert invoice.amount == Decimal("90.00")
    sent = [j for m, p, j in fake_paypal.calls if m == "POST" and p == "/v2/invoicing/invoices"][-1]
    assert sent["items"][0]["unit_amount"]["value"] == "90.00"


def test_jobs_chase_deposit_and_change_order_together_after_a_long_jump(api, session, fake_paypal):
    from datetime import timedelta

    from app import clock
    from app.jobs import run_daily_jobs
    from app.models import Reminder

    contract = active_contract(api)
    approve_change_order(
        session, fake_paypal, session.get(Contract, contract["id"]),
        description="Menu", estimated_hours=Decimal("1"), actor="user",
    )
    today = clock.today(session)
    first = run_daily_jobs(session, fake_paypal, today + timedelta(days=60))
    # both open invoices go overdue and get one final reminder each, not a burst
    assert len(first["overdue"]) == 2
    assert sorted(r["stage"] for r in first["reminders"]) == [14, 14]
    # the dated logo milestone is invoiced too, and a run on the same day changes nothing
    assert len(first["invoiced"]) == 1
    again = run_daily_jobs(session, fake_paypal, today + timedelta(days=60))
    assert again["invoiced"] == [] and again["overdue"] == [] and again["reminders"] == []
    assert len(session.exec(select(Reminder)).all()) == 2


def test_dated_milestone_whose_date_passed_gets_a_fresh_due_date(api, session, fake_paypal):
    from datetime import timedelta

    from app import clock
    from app.jobs import run_daily_jobs

    contract = api.post("/api/contracts", data={"client_email": "b@example.com", "text": CONTRACT_TEXT}).json()
    logo = contract["milestones"][1]
    today = clock.today(session)
    api.patch(f"/api/milestones/{logo['id']}", json={"due_date": (today - timedelta(days=3)).isoformat()})
    api.post(f"/api/contracts/{contract['id']}/approve", json={"deposit_pct": 0})
    run_daily_jobs(session, fake_paypal, today)
    invoice = session.exec(select(Invoice).where(Invoice.milestone_id == logo["id"])).one()
    assert invoice.due_date == today + timedelta(days=15)  # never a due date in the past
