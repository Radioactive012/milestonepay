"""Daily jobs: send dated invoices, mark late invoices overdue, and send PayPal reminders.

All of this is done by code on a fixed schedule. Nothing here is decided by the AI.
"""
from datetime import date, timedelta

from sqlmodel import Session, select

from app import audit
from app.billing import invoice_milestone
from app.milestones import move
from app.models import Contract, Invoice, Milestone, Reminder
from app.paypal.client import PayPalClient, PayPalError, paypal_reason
from app.paypal.invoices import remind_invoice

# days relative to the invoice due date
REMINDER_STAGES = (-3, 0, 3, 7, 14)
# dated milestones are invoiced this many days before their due date
INVOICE_LEAD_DAYS = 7


def reminder_text(days: int, invoice: Invoice) -> tuple[str, str]:
    amount = f"{invoice.currency} {invoice.amount}"
    due = invoice.due_date.strftime("%d %b %Y")
    if days < 0:
        return (
            f"Coming up: invoice {invoice.number}",
            f"A friendly reminder that invoice {invoice.number} for {amount} is due on {due}. Thank you!",
        )
    if days == 0:
        return (
            f"Due today: invoice {invoice.number}",
            f"Invoice {invoice.number} for {amount} is due today. You can pay it with the link in this invoice. Thank you!",
        )
    if days < 14:
        return (
            f"Overdue: invoice {invoice.number}",
            f"Invoice {invoice.number} for {amount} was due on {due} and is now {days} days overdue. "
            "Please pay it with the link in this invoice.",
        )
    return (
        f"Final reminder: invoice {invoice.number}",
        f"Invoice {invoice.number} for {amount} is {days} days overdue (due {due}). Please pay it now. "
        "If something is wrong with the work or the invoice, reply so we can sort it out.",
    )


def _send_dated_invoices(session: Session, paypal: PayPalClient, today: date, summary: dict) -> None:
    due_soon = session.exec(
        select(Milestone)
        .where(Milestone.status == "scheduled", Milestone.due_date <= today + timedelta(days=INVOICE_LEAD_DAYS))
        .order_by(Milestone.due_date)
    ).all()
    for milestone in due_soon:
        try:
            invoice = invoice_milestone(session, paypal, milestone, "system", today=today)
            summary["invoiced"].append(invoice.number)
        except PayPalError as error:
            session.rollback()
            summary["errors"].append(f"Invoice for '{milestone.title}' failed: {paypal_reason(error)}")


def _chase_open_invoices(session: Session, paypal: PayPalClient, today: date, summary: dict) -> None:
    rows = session.exec(
        select(Invoice, Milestone)
        .join(Milestone, Milestone.id == Invoice.milestone_id)
        .where(Invoice.status == "SENT", Milestone.status.in_(["invoiced", "overdue"]))
        .order_by(Invoice.due_date)
    ).all()
    for invoice, milestone in rows:
        days = (today - invoice.due_date).days
        if days > 0 and milestone.status == "invoiced":
            move(session, milestone, "overdue", "system", invoice_number=invoice.number, days_overdue=days)
            session.commit()
            summary["overdue"].append(invoice.number)

        reached = [stage for stage in REMINDER_STAGES if days >= stage]
        if not reached:
            continue
        # only the latest stage reached, so a jump of several days sends one reminder, not a burst
        stage = reached[-1]
        already_sent = session.exec(
            select(Reminder).where(Reminder.invoice_id == invoice.id, Reminder.stage == stage)
        ).first()
        if already_sent:
            continue

        subject, note = reminder_text(days, invoice)
        try:
            remind_invoice(paypal, invoice.paypal_invoice_id, subject, note)
        except PayPalError as error:
            if error.status_code == 429:
                reason = "PayPal allows only 2 reminders a day, so it will go out on a later run."
            else:
                reason = paypal_reason(error)
            summary["errors"].append(f"Reminder for {invoice.number} not sent yet: {reason}")
            continue
        session.add(Reminder(invoice_id=invoice.id, stage=stage, subject=subject, note=note))
        audit.record(
            session, milestone.contract_id, "system", "reminder_sent",
            number=invoice.number, stage=stage, days_from_due=days,
        )
        session.commit()
        summary["reminders"].append({"number": invoice.number, "stage": stage, "subject": subject})


def run_daily_jobs(session: Session, paypal: PayPalClient, today: date) -> dict:
    """Safe to run as often as you like: each invoice, overdue mark and reminder happens once."""
    summary = {"today": today.isoformat(), "invoiced": [], "overdue": [], "reminders": [], "errors": []}
    _send_dated_invoices(session, paypal, today, summary)
    _chase_open_invoices(session, paypal, today, summary)
    return summary
