from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete
from sqlmodel import Session, SQLModel

from app import audit, clock
from app.ai.llm import DailyAILimit, get_ai_limit
from app.api.contracts import contract_out, save_analysed_contract
from app.config import get_settings
from app.db import get_session
from app.demo_data import demo_contract
from app.jobs import run_daily_jobs
from app.models import AppState
from app.paypal.client import PayPalClient, get_paypal_client


def require_demo_mode() -> None:
    if not get_settings().demo_mode:
        raise HTTPException(status_code=404, detail="Demo controls are turned off.")


router = APIRouter(prefix="/api/demo", dependencies=[Depends(require_demo_mode)])


def _clock_out(session: Session, limit: DailyAILimit) -> dict:
    return {
        "offset_days": clock.offset_days(session),
        "today": clock.today(session),
        "ai_calls_today": limit.used_today(),
        "ai_daily_limit": limit.limit,
    }


@router.get("/clock")
def read_clock(session: Session = Depends(get_session), limit: DailyAILimit = Depends(get_ai_limit)):
    return _clock_out(session, limit)


class ClockUpdate(BaseModel):
    offset_days: int = Field(ge=0, le=365)


@router.post("/clock")
def set_clock(
    body: ClockUpdate, session: Session = Depends(get_session), limit: DailyAILimit = Depends(get_ai_limit)
):
    """Pretend it's this many days after the real date, for demos. 0 is the real date."""
    clock.set_offset(session, body.offset_days, "user")
    session.commit()
    return _clock_out(session, limit)


@router.post("/run-jobs")
def run_jobs_now(
    session: Session = Depends(get_session), paypal: PayPalClient = Depends(get_paypal_client)
):
    return run_daily_jobs(session, paypal, clock.today(session))


@router.post("/load", status_code=201)
def load_demo_project(session: Session = Depends(get_session)):
    """Add the Harbor Lane Bakery demo contract as a draft, using a saved AI reading (no AI credit used)."""
    text, analysis = demo_contract(clock.today(session))
    contract = save_analysed_contract(
        session, analysis, text, None, get_settings().demo_client_email, None, actor="system"
    )
    audit.record(session, contract.id, "system", "demo_project_loaded", note="saved example of the AI's reading")
    session.commit()
    return contract_out(session, contract)


@router.post("/reset")
def reset_demo(session: Session = Depends(get_session), limit: DailyAILimit = Depends(get_ai_limit)):
    """Delete every project, message and invoice record, and set the clock back to today.

    Today's AI usage count is kept, so a reset can't be used to get around the daily limit.
    Invoices already sent to the PayPal sandbox stay there.
    """
    for table in reversed(SQLModel.metadata.sorted_tables):
        if table.name != AppState.__tablename__:
            session.exec(delete(table))
    clock.set_offset(session, 0, "user")
    session.commit()
    return {"status": "reset", **_clock_out(session, limit)}
