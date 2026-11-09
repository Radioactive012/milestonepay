from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session

from app import clock
from app.config import get_settings
from app.db import get_session
from app.jobs import run_daily_jobs
from app.paypal.client import PayPalClient, get_paypal_client


def require_demo_mode() -> None:
    if not get_settings().demo_mode:
        raise HTTPException(status_code=404, detail="Demo controls are turned off.")


router = APIRouter(prefix="/api/demo", dependencies=[Depends(require_demo_mode)])


def _clock_out(session: Session) -> dict:
    return {"offset_days": clock.offset_days(session), "today": clock.today(session)}


@router.get("/clock")
def read_clock(session: Session = Depends(get_session)):
    return _clock_out(session)


class ClockUpdate(BaseModel):
    offset_days: int = Field(ge=0, le=365)


@router.post("/clock")
def set_clock(body: ClockUpdate, session: Session = Depends(get_session)):
    """Pretend it's this many days after the real date, for demos. 0 is the real date."""
    clock.set_offset(session, body.offset_days, "user")
    session.commit()
    return _clock_out(session)


@router.post("/run-jobs")
def run_jobs_now(
    session: Session = Depends(get_session), paypal: PayPalClient = Depends(get_paypal_client)
):
    return run_daily_jobs(session, paypal, clock.today(session))
