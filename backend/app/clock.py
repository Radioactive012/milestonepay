from datetime import date, timedelta

from sqlmodel import Session

from app import audit
from app.models import AppState


def offset_days(session: Session) -> int:
    state = session.get(AppState, 1)
    return state.clock_offset_days if state else 0


def today(session: Session) -> date:
    """The app's idea of today: the real date plus the demo clock offset."""
    return date.today() + timedelta(days=offset_days(session))


def set_offset(session: Session, days: int, actor: str) -> None:
    state = session.get(AppState, 1) or AppState(id=1)
    old = state.clock_offset_days
    state.clock_offset_days = days
    session.add(state)
    audit.record(session, None, actor, "demo_clock_set", old_offset=old, new_offset=days)
