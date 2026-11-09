from app.ai.llm import AIError
from tests.conftest import CONTRACT_TEXT


def create(api, **form):
    data = {"client_email": "buyer@example.com", "text": CONTRACT_TEXT}
    data.update(form)
    return api.post("/api/contracts", data=data)


def paid_event(event_id, paypal_invoice_id):
    return {
        "id": event_id,
        "event_type": "INVOICING.INVOICE.PAID",
        "resource": {"invoice": {"id": paypal_invoice_id, "status": "PAID"}},
    }


def test_create_contract_saves_checked_drafts(api, fake_ai):
    response = create(api)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "draft"
    assert body["client_name"] == "Harbor Lane Bakery"
    assert [m["status"] for m in body["milestones"]] == ["draft", "draft", "draft"]
    assert body["milestone_total"] == "3200.00"
    assert len(body["risks"]) == 1
    assert body["deposit_pct_suggested"] == 30
    assert body["audit"][0]["actor"] == "ai"
    assert fake_ai.calls[0]["text"] == CONTRACT_TEXT.strip()


def test_contract_needs_text_or_file_and_an_email(api):
    assert api.post("/api/contracts", data={"client_email": "buyer@example.com"}).status_code == 422
    assert create(api, client_email="not-an-email").status_code == 422


def test_ai_failure_returns_readable_error(api, fake_ai):
    def fail(**kwargs):
        raise AIError("The AI is rate limited right now. Try again in a minute.")

    fake_ai.analyse = fail
    response = create(api)
    assert response.status_code == 502
    assert "rate limited" in response.json()["detail"]


def test_uploaded_file_is_passed_to_the_ai(api, fake_ai):
    response = api.post(
        "/api/contracts",
        data={"client_email": "buyer@example.com"},
        files={"file": ("contract.png", b"\x89PNG fake", "image/png")},
    )
    assert response.status_code == 201
    assert fake_ai.calls[0]["media_type"] == "image/png"
    assert fake_ai.calls[0]["file_bytes"] == b"\x89PNG fake"


def test_edit_draft_milestone(api):
    contract = create(api).json()
    milestone_id = contract["milestones"][0]["id"]
    body = api.patch(f"/api/milestones/{milestone_id}", json={"amount": "900.00"}).json()
    assert body["milestones"][0]["amount"] == "900.00"
    assert api.patch(f"/api/milestones/{milestone_id}", json={"amount": "-1"}).status_code == 422


def test_full_flow_deposit_trigger_and_payment(api, fake_paypal):
    contract = create(api).json()
    approved = api.post(f"/api/contracts/{contract['id']}/approve", json={"deposit_pct": 30})
    assert approved.status_code == 200
    body = approved.json()
    assert body["status"] == "active"

    deposit, sketches, logo, kit = body["milestones"]
    assert deposit["is_deposit"] and deposit["amount"] == "960.00"
    assert deposit["status"] == "invoiced"
    assert deposit["invoice"]["payer_url"] == "https://pay.example/INV2-0001"
    assert [sketches["amount"], logo["amount"], kit["amount"]] == ["560.00", "980.00", "700.00"]
    assert body["milestone_total"] == "3200.00"
    assert [sketches["status"], logo["status"], kit["status"]] == ["awaiting_trigger", "scheduled", "awaiting_trigger"]
    sent = fake_paypal.invoices["INV2-0001"]
    assert sent["status"] == "SENT"
    assert sent["payload"]["items"][0]["unit_amount"] == {"currency_code": "USD", "value": "960.00"}
    assert sent["payload"]["primary_recipients"][0]["billing_info"]["email_address"] == "buyer@example.com"

    assert api.post(f"/api/contracts/{contract['id']}/approve", json={"deposit_pct": 30}).status_code == 409

    triggered = api.post(f"/api/milestones/{sketches['id']}/invoice").json()
    assert triggered["milestones"][1]["status"] == "invoiced"
    assert api.post(f"/api/milestones/{sketches['id']}/invoice").status_code == 409

    event = paid_event("WH-1", "INV2-0001")
    assert api.post("/webhooks/paypal", json=event).json() == {"status": "ok"}
    assert api.post("/webhooks/paypal", json=event).json() == {"status": "duplicate"}

    final = api.get(f"/api/contracts/{contract['id']}").json()
    assert final["milestones"][0]["status"] == "paid"
    assert final["milestones"][0]["invoice"]["status"] == "PAID"
    actions = [entry["action"] for entry in final["audit"]]
    assert "invoice_paid" in actions
    assert actions.count("invoice_sent") == 2


def test_approve_without_deposit(api, fake_paypal):
    contract = create(api).json()
    body = api.post(f"/api/contracts/{contract['id']}/approve", json={"deposit_pct": 0}).json()
    assert len(body["milestones"]) == 3
    assert fake_paypal.invoices == {}


def test_deposit_invoice_failure_can_be_retried(api, fake_paypal):
    contract = create(api).json()
    fake_paypal.fail_create = True
    response = api.post(f"/api/contracts/{contract['id']}/approve", json={"deposit_pct": 25})
    assert response.status_code == 502
    assert "Send invoice now" in response.json()["detail"]
    assert "sandbox is down" in response.json()["detail"]

    body = api.get(f"/api/contracts/{contract['id']}").json()
    deposit = body["milestones"][0]
    assert body["status"] == "active" and deposit["status"] == "draft"

    fake_paypal.fail_create = False
    retried = api.post(f"/api/milestones/{deposit['id']}/invoice").json()
    assert retried["milestones"][0]["status"] == "invoiced"


def test_refresh_reads_status_from_paypal(api, fake_paypal):
    contract = create(api).json()
    body = api.post(f"/api/contracts/{contract['id']}/approve", json={"deposit_pct": 30}).json()
    invoice_id = body["milestones"][0]["invoice"]["id"]
    fake_paypal.invoices["INV2-0001"]["status"] = "PAID"
    refreshed = api.post(f"/api/invoices/{invoice_id}/refresh").json()
    assert refreshed["milestones"][0]["status"] == "paid"


def test_webhook_for_unknown_invoice_is_stored_and_ignored(api):
    response = api.post("/webhooks/paypal", json=paid_event("WH-9", "INV2-UNKNOWN"))
    assert response.json() == {"status": "ok"}
