# MilestonePay

An AI agent that protects a freelancer's money from contract to cash. Built for the
[PayPal AI Hackathon](https://paypalaihackathon.devpost.com/).

The AI reads contracts and client messages and proposes actions. The code moves the
money through PayPal (sandbox only), and the freelancer approves every step.

## Status

Work in progress. The hackathon build period is 1-12 Nov 2026. This README will be
filled in with setup steps, a hosted demo link, and a judge walkthrough.

## Planned features

- Contract risk check with suggested rewrites and a deposit suggestion
- Milestone extraction from a pasted contract, PDF or photo
- Scope-creep detection on client messages, with priced change orders
- PayPal invoices created, sent and tracked through webhooks
- Client portal where files stay locked until the invoice is paid
- PayPal-native reminders and an audit log

## Tech

Python and FastAPI backend, React and TypeScript frontend, DeepSeek V4.1 Flash through
OpenRouter for the AI steps, PayPal Invoicing and Webhooks (sandbox), AG Grid, Postgres,
hosted on Render.

## Setup

Copy `.env.example` to `.env` and add your own PayPal sandbox and OpenRouter keys.

Backend (Python 3.11 or newer):

```bash
cd backend
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest
.venv/bin/uvicorn app.main:app --reload
```

The app only talks to the PayPal sandbox and refuses to start against live mode.
To check your sandbox keys, run `.venv/bin/python -m scripts.paypal_spike <sandbox-buyer-email>`
from the `backend` folder. Full run instructions for the whole app will be added here.

## License

[MIT](LICENSE)
