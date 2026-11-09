def test_health(api):
    assert api.get("/health").json()["status"] == "ok"


def test_bad_signature_is_rejected(api, fake_paypal):
    fake_paypal.webhooks_valid = False
    response = api.post("/webhooks/paypal", json={"id": "E1"})
    assert response.status_code == 400


def test_invalid_json_is_rejected(api):
    response = api.post("/webhooks/paypal", content=b"not json")
    assert response.status_code == 400


def test_valid_event_is_accepted_once(api):
    event = {"id": "E1", "event_type": "INVOICING.INVOICE.PAID"}
    assert api.post("/webhooks/paypal", json=event).json() == {"status": "ok"}
    assert api.post("/webhooks/paypal", json=event).json() == {"status": "duplicate"}


def test_event_without_id_is_ignored(api):
    assert api.post("/webhooks/paypal", json={"event_type": "X"}).json() == {"status": "ignored"}


def test_paypal_failure_during_check_returns_502_not_a_crash(api, fake_paypal):
    from app.paypal.client import PayPalError

    def broken(headers, event):
        raise PayPalError(401, "PayPal sandbox keys are missing.")

    fake_paypal.verify_webhook = broken
    response = api.post("/webhooks/paypal", json={"id": "E1"})
    assert response.status_code == 502
    assert "keys are missing" in response.json()["detail"]
