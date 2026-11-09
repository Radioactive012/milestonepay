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

Python and FastAPI backend, React and TypeScript frontend, Claude for the AI steps,
PayPal Invoicing and Webhooks (sandbox), AG Grid, Postgres, hosted on Render.

## Setup

Copy `.env.example` to `.env` and add your own PayPal sandbox and Anthropic keys.
Full run instructions will be added here.

## License

[MIT](LICENSE)
