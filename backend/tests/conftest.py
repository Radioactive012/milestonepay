import re

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.ai.contract import get_contract_ai
from app.ai.llm import DailyAILimit, get_ai_limit
from app.ai.schemas import ContractAnalysis
from app.db import get_session, init_db, make_engine
from app.main import app
from app.paypal.client import get_paypal_client

CONTRACT_TEXT = """\
Design agreement between Meera Iyer (Designer) and Harbor Lane Bakery (Client).
Total fee: USD 3,200.
1. Sketches: $800, due when the Client approves the sketches.
2. Final logo: $1,400, due on 2026-12-01.
3. Brand kit: $1,000, due on delivery of the brand kit.
Payment is due upon client satisfaction with the work.
The Client may request unlimited revisions.
"""


def sample_analysis(**overrides) -> ContractAnalysis:
    data = {
        "transcription": "",
        "client_name": "Harbor Lane Bakery",
        "currency": "usd",
        "stated_total": 3200,
        "payment_terms_days": 15,
        "milestones": [
            {
                "title": "Sketches",
                "amount": 800,
                "trigger": "event",
                "due_date": None,
                "trigger_description": "Client approves the sketches",
                "revision_limit": None,
                "source_quote": "Sketches: $800, due when the Client approves the sketches.",
            },
            {
                "title": "Final logo",
                "amount": 1400,
                "trigger": "date",
                "due_date": "2026-12-01",
                "trigger_description": "Due on 1 Dec 2026",
                "revision_limit": None,
                "source_quote": "Final logo: $1,400, due on 2026-12-01.",
            },
            {
                "title": "Brand kit",
                "amount": 1000,
                "trigger": "event",
                "due_date": None,
                "trigger_description": "Brand kit delivered",
                "revision_limit": None,
                "source_quote": "Brand kit: $1,000, due on delivery of the brand kit.",
            },
        ],
        "risks": [
            {
                "clause_quote": "Payment is due upon client satisfaction with the work.",
                "category": "vague_acceptance",
                "severity": "high",
                "why_it_matters": "The client can refuse to pay by saying they are not satisfied.",
                "suggested_rewrite": "Payment is due within 15 days of delivery.",
            },
            {
                "clause_quote": "The Designer transfers all rights before any payment.",
                "category": "ip_before_payment",
                "severity": "high",
                "why_it_matters": "Made up by the model; not in the contract.",
                "suggested_rewrite": "Rights transfer on full payment.",
            },
        ],
        "deposit_pct": 30,
        "deposit_rationale": "Payment depends on satisfaction.",
        "ambiguities": ["What counts as delivery of the brand kit?"],
    }
    data.update(overrides)
    return ContractAnalysis.model_validate(data)


class FakeAI:
    def __init__(self, analysis: ContractAnalysis | None = None):
        self.analysis = analysis or sample_analysis()
        self.calls = []

    def analyse(self, *, text, file_bytes, media_type):
        self.calls.append({"text": text, "file_bytes": file_bytes, "media_type": media_type})
        return self.analysis


class FakePayPal:
    def __init__(self):
        self.invoices: dict[str, dict] = {}
        self.calls: list[tuple] = []
        self.webhooks_valid = True
        self.fail_create = False
        self.fail_remind = False
        self.reminders: list[tuple[str, dict]] = []

    def request(self, method, path, json=None, **kwargs):
        from app.paypal.client import PayPalError

        self.calls.append((method, path, json))
        if method == "POST" and path == "/v2/invoicing/invoices":
            if self.fail_create:
                raise PayPalError(500, "sandbox is down")
            invoice_id = f"INV2-{len(self.invoices) + 1:04d}"
            self.invoices[invoice_id] = {
                "id": invoice_id,
                "status": "DRAFT",
                "payload": json,
                "detail": {"metadata": {"recipient_view_url": f"https://pay.example/{invoice_id}"}},
            }
            return {"href": f"https://api-m.sandbox.paypal.com/v2/invoicing/invoices/{invoice_id}"}
        match = re.fullmatch(r"/v2/invoicing/invoices/([^/]+)(/send|/remind)?", path)
        if match and match.group(2) == "/send":
            self.invoices[match.group(1)]["status"] = "SENT"
            return {}
        if match and match.group(2) == "/remind":
            if self.fail_remind:
                raise PayPalError(500, "sandbox is down")
            self.reminders.append((match.group(1), json))
            return {}
        if match and method == "GET":
            return self.invoices[match.group(1)]
        raise AssertionError(f"Unexpected PayPal call {method} {path}")

    def verify_webhook(self, headers, event):
        return self.webhooks_valid


@pytest.fixture
def engine():
    engine = make_engine("sqlite://")
    init_db(engine)
    return engine


@pytest.fixture
def session(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture
def fake_paypal():
    return FakePayPal()


@pytest.fixture
def fake_ai():
    return FakeAI()


@pytest.fixture
def api(engine, fake_paypal, fake_ai):
    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_paypal_client] = lambda: fake_paypal
    app.dependency_overrides[get_contract_ai] = lambda: fake_ai
    app.dependency_overrides[get_ai_limit] = lambda: DailyAILimit(engine, 150)
    yield TestClient(app)
    app.dependency_overrides.clear()
