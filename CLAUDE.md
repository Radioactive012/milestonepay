# MilestonePay

A hackathon project for the PayPal AI Hackathon (deadline Fri 13 Nov 2026, 01:30 IST).
An AI agent that protects a freelancer's money from contract to cash: Claude reads
contracts and client messages and proposes actions, our code moves money through
PayPal (sandbox only), and the freelancer approves every step.

## The team

Two people, each using Claude Code on their own Mac, both pushing to `main`.

- **Person A: Vinayak** (GitHub `Radioactive012`). Owns PayPal, the database, money
  flow, client portal and deploy.
- **Person B: Avirup** (GitHub `avirupmac7-blip`). Owns the AI prompts, the web
  screens, test contracts and messages, and the demo video.

Both are new to GitHub and to some technical terms. Explain things in plain words,
say what a command will do before running it, and avoid jargon.

## Who edits what

| Area | Owner |
|---|---|
| `backend/app/paypal/`, `backend/app/billing.py`, `backend/app/milestones.py` | A |
| `backend/scripts/`, deploy files, client portal screens (`frontend/src/pages/portal/`) | A |
| `backend/app/ai/`, `backend/evals/`, `frontend/` (except the portal) | B |
| `backend/app/models.py`, `backend/app/db.py`, `backend/app/api/`, `requirements.txt`, `CLAUDE.md`, `README.md` | Shared |

Before changing a file the other person owns, or a shared file, tell the user so they
can check with their teammate first. Never delete or rewrite the other person's work.

## Rules that always apply

- PayPal **sandbox only**. `Settings.paypal_base_url` refuses anything else; keep it that way.
- Never commit `.env`, API keys, client secrets or tokens. Never print them either.
- The AI never calls PayPal and never sets a final amount. It only reads and proposes;
  code does the money work after the freelancer approves.
- Money is `Decimal`, rounded half up to 2 places. Never `float` for stored amounts.
- Milestone status changes only through `app.milestones.move()`, which enforces the
  allowed steps and writes the audit log.
- Every action that matters gets an audit entry saying who did it
  (`user`, `client`, `system`, `ai`, `paypal`).
- Quotes the AI returns must exist word for word in the source text
  (`app.ai.guardrails.quote_in_source`).
- Use `claude-opus-5-5` unless `ANTHROPIC_MODEL` says otherwise.

## Daily git routine

1. Before starting: `git pull` on `main`.
2. Work in small pieces.
3. Before pushing: run the tests (they must pass), then `git pull` again, then commit and push.
4. Add a line to the "Notes for each other" section in `docs/TASKS.md` saying what changed.
5. If `git pull` reports a conflict, stop and explain it to the user in plain words
   before changing anything.

Never force-push, never rewrite history on `main`, never delete branches without asking.

## Commands

Backend setup (Python 3.11 or newer, from the `backend` folder):

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Run tests: `.venv/bin/python -m pytest`
Run the API locally: `.venv/bin/uvicorn app.main:app --reload`
Check real PayPal sandbox keys: `.venv/bin/python -m scripts.paypal_spike <sandbox-buyer-email>`

Secrets live in `.env` at the project root (copy `.env.example`). Each person keeps their own.

## Where things are

- `docs/TASKS.md`: schedule, task split, what's done, and notes for each other
- `backend/app/main.py`: the FastAPI app
- `backend/app/api/contracts.py`: contract, milestone and invoice routes
- `backend/app/ai/`: Claude prompt, output schema, code checks on the AI's answer
- `backend/app/billing.py`: creating, sending and syncing PayPal invoices
- `backend/app/paypal/`: PayPal API client, invoice helpers, webhook route
- `backend/tests/`: tests use a pretend PayPal and a pretend AI (see `conftest.py`)

Personal notes for your own Claude only go in `CLAUDE.local.md`, which git ignores.
