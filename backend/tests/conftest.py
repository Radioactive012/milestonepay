import os
import re

# Tests never read anyone's .env or real keys: no real PayPal, no real AI credit spent.
# This must run before anything imports app.config.
os.environ["MILESTONEPAY_ENV_FILE"] = ""
for _key in (
    "PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET", "PAYPAL_WEBHOOK_ID", "PAYPAL_ENVIRONMENT",
    "OPENROUTER_API_KEY", "AI_MODEL", "AI_DAILY_LIMIT", "DATABASE_URL", "DEMO_MODE",
    "DEMO_CLIENT_EMAIL", "JOBS_INTERVAL_MINUTES", "APP_PASSWORD",
):
    os.environ.pop(_key, None)

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel

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

    def verify_webhook(self, headers, raw_body):
        return self.webhooks_valid


# Set TEST_DATABASE_URL to run every test against Postgres instead of an in-memory SQLite.
# Every table in that database is dropped before each test, so never point it at real data.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture
def engine():
    if TEST_DATABASE_URL:
        import app.models  # noqa: F401  registers the tables

        engine = make_engine(TEST_DATABASE_URL)
        SQLModel.metadata.drop_all(engine)
    else:
        engine = make_engine("sqlite://")
    init_db(engine)
    yield engine
    engine.dispose()


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
def api(engine, fake_paypal, fake_ai, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "app_password", "")
    monkeypatch.setattr(get_settings(), "demo_mode", True)

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_paypal_client] = lambda: fake_paypal
    app.dependency_overrides[get_contract_ai] = lambda: fake_ai
    app.dependency_overrides[get_ai_limit] = lambda: DailyAILimit(engine, 150)
    yield TestClient(app)
    app.dependency_overrides.clear()
