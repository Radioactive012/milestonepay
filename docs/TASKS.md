# Team tasks and schedule

Deadline: Fri 13 Nov 2026, 01:30 IST. Submission target: Thu 12 Nov, 20:00 IST.
Code freeze: Thu 12 Nov, 12:00 IST.

**Person A** (Vinayak): PayPal, data, deploy.
**Person B** (Avirup): AI, UI, story.
Roles can be swapped. Whoever owns an area decides inside it. Anything that changes
a database table or an API route needs both people.

## Notes for each other

Newest at the top. One line per push: who, what changed, anything the other must do.

- Vinayak: added `message`, `suggestion`, `change_order` tables, `contract.hourly_rate`
  (default 40, `PATCH /api/contracts/{id}`), `milestone.revisions_used`,
  `approve_change_order()` and `record_revision()`. Avirup: your routes can call these
  (see "Money functions to call" in CLAUDE.md). Delete `backend/milestonepay.db` after
  pulling, because the tables changed. Also: `hours.quantize(Decimal("0.25"))` rounds to
  2 decimals, not to quarter hours; use `app.billing.round_to_quarter_hour`.
- Vinayak: added GitHub comment rules to `CLAUDE.md`.

- Vinayak: added `CLAUDE.md` (team rules both our Claudes read automatically). Please `git pull`.
- Vinayak: backend foundation is on `main`: PayPal invoices, contract reading with
  Claude, deposit, paid webhook. Needs real keys to test.

## Compressed schedule (4 days)

| Day | Person A | Person B |
|---|---|---|
| Mon 9 Nov | PayPal sandbox US business and personal accounts, app credentials, `.env`. Run `scripts/paypal_spike.py` end to end. | Anthropic key with spend limit. Write the 10 contracts and 15 messages with expected answers. First contract extraction and risk prompts. |
| Tue 10 Nov | Database tables, contract and milestone routes, webhook updates milestone status, deploy to Render + Neon, register webhook. | New project page (paste contract, risks, milestone grid, approve). Message analysis prompt. |
| Wed 11 Nov | Client portal, deliverable upload, files unlock on paid webhook, PayPal reminders, demo clock. Core freeze at night. | Approval inbox, change orders, AG Grid tables, audit timeline, eval run. |
| Thu 12 Nov | Code freeze 12:00. README, hosted demo check, repo and license check. | Video (under 3 minutes), Devpost text. Submit by 20:00. |

## Cut from the original plan

Dispute evidence pack, Bryntum timeline, APIMatic SDK and the agentic commerce
extra only come back if the core works by Wednesday night. AG Grid and Render stay.

## Done so far

- Public repo with MIT license
- FastAPI backend skeleton, PayPal client (token cache, invoices, reminders,
  webhook signature check), webhook route, 14 passing tests
- `backend/scripts/paypal_spike.py` to prove the PayPal flow with real sandbox keys
- Database tables (contracts, milestones, invoices, webhook events, audit log),
  SQLite locally and Postgres when `DATABASE_URL` is set
- Milestone status rules: only allowed changes, each one written to the audit log
- AI contract reading with Claude (text, PDF or photo): milestones, risky clauses,
  deposit suggestion. Code checks drop clauses not quoted word for word, warn when
  amounts don't add up, and reject zero amounts
- Routes: create contract, edit draft milestone, approve with deposit (deposit
  invoice goes out through PayPal), send milestone invoice, refresh from PayPal
- PayPal "paid" webhook marks the invoice and milestone paid, stored so repeats are ignored
- 36 passing tests, all with a pretend PayPal and a pretend AI

## Not done yet

- Not yet run against real PayPal sandbox or the real Claude API (needs keys)
- Client messages and scope-creep detection, client portal, file unlock,
  reminders, frontend, deploy
