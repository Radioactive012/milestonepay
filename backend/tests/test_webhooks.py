import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.paypal import webhooks
from app.paypal.client import get_paypal_client


class FakePayPal:
    def __init__(self, valid: bool):
        self.valid = valid

    def verify_webhook(self, headers, event):
        return self.valid


@pytest.fixture(autouse=True)
def reset_state():
    webhooks._seen_event_ids.clear()
    yield
    app.dependency_overrides.clear()


def use_paypal(valid: bool) -> TestClient:
    app.dependency_overrides[get_paypal_client] = lambda: FakePayPal(valid)
    return TestClient(app)


def test_health():
    assert TestClient(app).get("/health").json()["status"] == "ok"


def test_bad_signature_is_rejected():
    response = use_paypal(False).post("/webhooks/paypal", json={"id": "E1"})
    assert response.status_code == 400


def test_invalid_json_is_rejected():
    response = use_paypal(True).post("/webhooks/paypal", content=b"not json")
    assert response.status_code == 400


def test_valid_event_is_accepted_once():
    client = use_paypal(True)
    event = {"id": "E1", "event_type": "INVOICING.INVOICE.PAID"}
    assert client.post("/webhooks/paypal", json=event).json() == {"status": "ok"}
    assert client.post("/webhooks/paypal", json=event).json() == {"status": "duplicate"}
