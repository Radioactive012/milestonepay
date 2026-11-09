"""The demo project: a contract plus a saved example of the AI's reading of it.

Loading it costs no AI credit, so judges can explore the whole flow for free.
Dates are relative to the app's today, so the demo works whenever it's loaded.
"""
from datetime import date, timedelta

from app.ai.schemas import ContractAnalysis


def demo_contract(today: date) -> tuple[str, ContractAnalysis]:
    logo_due = (today + timedelta(days=21)).isoformat()
    text = f"""Design agreement between Meera Iyer (Designer) and Harbor Lane Bakery (Client).
Total fee: USD 3,200.
1. Sketches: $800, due when the Client approves the sketches.
2. Final logo: $1,400, due on {logo_due}.
3. Brand kit: $1,000, due on delivery of the brand kit.
Scope: a logo and a brand kit (colours, fonts, business card).
Payment is due upon client satisfaction with the work.
The Client may request unlimited revisions.
All rights in the work pass to the Client on delivery.
Invoices are payable within 15 days."""

    analysis = ContractAnalysis.model_validate(
        {
            "transcription": "",
            "client_name": "Harbor Lane Bakery",
            "currency": "USD",
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
                    "due_date": logo_due,
                    "trigger_description": f"Due on {logo_due}",
                    "revision_limit": None,
                    "source_quote": f"Final logo: $1,400, due on {logo_due}.",
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
                    "why_it_matters": "The client can refuse to pay just by saying they aren't satisfied.",
                    "suggested_rewrite": "Payment is due within 15 days of delivery. The client has 5 days "
                    "to list specific changes; after that the work counts as accepted.",
                },
                {
                    "clause_quote": "The Client may request unlimited revisions.",
                    "category": "unlimited_revisions",
                    "severity": "high",
                    "why_it_matters": "Endless changes turn a fixed price into unpaid work.",
                    "suggested_rewrite": "Two rounds of revisions are included. Further rounds are billed "
                    "at the hourly rate.",
                },
                {
                    "clause_quote": "All rights in the work pass to the Client on delivery.",
                    "category": "ip_before_payment",
                    "severity": "high",
                    "why_it_matters": "The client owns the work before paying, so you lose your leverage.",
                    "suggested_rewrite": "All rights in the work pass to the Client once every invoice is paid in full.",
                },
            ],
            "deposit_pct": 30,
            "deposit_rationale": "Payment depends on the client's satisfaction and rights pass on delivery, "
            "so take part of the fee before starting.",
            "ambiguities": [
                "What exactly counts as delivery of the brand kit?",
                "The contract doesn't say what happens if the client cancels part-way.",
            ],
        }
    )
    return text, analysis
