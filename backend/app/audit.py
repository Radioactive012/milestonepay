import json

from sqlmodel import Session

from app.models import AuditEntry


def record(session: Session, contract_id: int | None, actor: str, action: str, **details) -> None:
    session.add(
        AuditEntry(
            contract_id=contract_id,
            actor=actor,
            action=action,
            details_json=json.dumps(details, default=str),
        )
    )
