# Proposal: client messages, suggestions and change orders

**Status: agreed by Vinayak on 9 Nov, with the changes listed under "Decisions" below.**

From Avirup (B) to Vinayak (A). `docs/TASKS.md` says table and route changes need both of us,
so please reply with OK or changes before either of us builds on this.

## What it enables

Demo story step 3: the client writes "Sketches approved! Could you also add a matching menu design?",
the AI proposes two things (invoice the Sketches milestone, and a change order for the menu), and the
freelancer approves or edits each one in an inbox. The AI only proposes; your code moves the money.

## New tables

| Table | Fields |
|---|---|
| message | id, contract_id, sender (client / freelancer / pasted), body, analysis_json, created_at |
| suggestion | id, contract_id, message_id, type (milestone_reached / scope_creep / extra_revision), payload_json, evidence_quote, confidence, status (pending / approved / dismissed), created_at |
| change_order | id, contract_id, message_id, description, estimated_hours, price, status (draft / invoiced / cancelled), invoice_id |

Reminders and late fees come later and reuse `suggestion` with new types.

## New routes

| Route | Does | Built by |
|---|---|---|
| `POST /api/messages` | Saves a message and runs `app/ai/messages.py`. Creates suggestions from the checked result. | B |
| `GET /api/suggestions?status=pending` | The approval inbox | B |
| `POST /api/suggestions/{id}/dismiss` | Marks it dismissed and writes an audit entry | B |
| `POST /api/suggestions/{id}/approve` | `milestone_reached`: moves the milestone and calls your `invoice_milestone`. `scope_creep`: creates a change order, and an invoice through your invoice service. Accepts edits (hours, description). | B writes the route, A's services do the money |

## Rules that stay in code

- Quotes are checked word for word against the message and contract before a suggestion is saved. Failures are dropped and logged to the audit log.
- Price = estimated hours x the freelancer's hourly rate, set by code. The AI never states a price.
- Suggestions under 0.6 confidence are shown as "Possible", with no approve button.
- Every approval writes an audit entry, and only your `move()` changes a milestone status.

## Already written (on my branch, not merged)

- `backend/app/ai/messages.py`: schemas, prompt, `check_message_analysis`, Claude client
- `backend/evals/`: 10 contracts and 15 messages with expected answers, and `run_evals.py`
- `frontend/`: the new project page against your existing routes

## Questions for you

1. Are you happy with those three tables, or do you want other names or fields?
2. Where should the hourly rate live? I used a constant of 40 in the evals. The plan has a `settings` table with the rate in it. Do you want to add that table, or should I?
3. The AI needs revisions used per milestone. We only store `revision_limit`. OK to add `revisions_used` to `milestone`, updated when I save a revision suggestion?
4. Should I write the message and suggestion routes (my suggestion above), or do you want them in your files?

## Decisions (Vinayak, 9 Nov)

1. Tables are OK with two changes: `suggestion` gets a nullable `milestone_id`. When a change order is
   approved, it creates a new milestone and invoices that through `invoice_milestone`, so webhooks, file
   unlock and reminders work for free. `change_order` stores `suggestion_id`, `description`,
   `estimated_hours`, `price` and `milestone_id` instead of its own invoice.
2. The hourly rate lives on `contract` as `hourly_rate` (default 40), editable on the new project page.
3. `milestone.revisions_used` is added, and only increased when the freelancer approves a revision suggestion.
4. Vinayak adds the tables, fields and an `approve_change_order()` money function in his files and says
   when they are pushed. Avirup writes the four routes in a new `backend/app/api/messages.py` and calls
   his functions.
