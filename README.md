# MilestonePay

**From contract to cash, without getting stiffed.**

MilestonePay is an AI agent that protects a freelancer's money at every step of a project.
The AI reads contracts and client messages and proposes what to do. Our code moves the money
through PayPal, and the freelancer approves every step that costs or collects money.

Built for the [PayPal AI Hackathon](https://paypalaihackathon.devpost.com/). PayPal runs in
**sandbox mode only**, so no real money ever moves.

- **Hosted demo:** https://milestonepay.onrender.com (login below, under Try it)
- **Demo video:** _add the public YouTube link here_ (the hackathon rules require YouTube)

## The problem

Freelancers who find their own clients lose money in predictable ways:

- vague contracts ("payment upon client satisfaction", unlimited revisions)
- "small extras" that turn into unpaid work (scope creep)
- clients who pay late, or disappear once they have the files

## What it does

| Stage | What happens |
|---|---|
| **Before signing** | Paste a contract, upload a PDF, or upload a photo of one. The AI lists the payment milestones, flags risky clauses with a fairer rewrite for each, and suggests a deposit. |
| **Approval** | The freelancer reviews and edits the milestones, then approves. The deposit invoice goes out through PayPal at once. |
| **During the work** | Client messages are read against the contract. The AI spots approved milestones, out-of-scope requests (priced as change orders at the freelancer's hourly rate) and extra revision rounds. Each one waits in an approval inbox. |
| **Delivery** | The client gets a private page with milestones, PayPal payment buttons and watermarked previews of the files. The full files unlock automatically when PayPal reports the invoice paid. |
| **After delivery** | Dated milestones are invoiced a week early, late invoices are marked overdue, and PayPal reminders go out 3 days before, on the due day, and 3, 7 and 14 days late. |

## How it uses PayPal

All calls go to the PayPal **sandbox** (`api-m.sandbox.paypal.com`). The app refuses to start
against live PayPal.

- **OAuth 2.0** client credentials, with the token cached and reused
- **Invoicing v2**: create a draft, send it, read its status, send reminders
  (`/v2/invoicing/invoices`, `/send`, `/remind`)
- **Webhooks**: `INVOICING.INVOICE.PAID`, `.CANCELLED` and `.REFUNDED` update the milestone.
  Every event's signature is checked with `/v1/notifications/verify-webhook-signature`, and
  repeated events are ignored.
- **Reconciliation**: a "Check payment" button reads the invoice from PayPal directly, in
  case a webhook is missed.

Deposits, milestone payments and change orders are all real PayPal sandbox invoices, paid on
PayPal's own payment page.

## How it uses AI

The AI is **DeepSeek V4.1 Flash 1017** (`deepseek/deepseek-v4.1-flash-1017`) through
**OpenRouter**. It has three jobs:

1. **Read a contract**: milestones, risky clauses with rewrites, a deposit suggestion, and
   points to clarify. PDFs are turned into text on our server; photos go to the model.
2. **Read a client message**: approved milestones, out-of-scope requests with an hours
   estimate, and revision requests.
3. **Explain itself**: every finding quotes the contract or message it's based on.

Every answer must match a strict JSON schema, and code checks it before anything is saved.

See the [architecture diagram](docs/architecture.md) for how the pieces fit together.

## How it uses AG Grid

Four tables in the app are AG Grid (Community edition), each doing real work:

- **Milestone review table** (New project page): the freelancer fixes what the AI read, right
  in the table. Title, amount, "paid when" (a dropdown) and due date are editable while the
  contract is a draft, and each edit saves at once. Amounts must be above zero, a date-based
  milestone without a date turns red, and a pinned **Total** row updates after every edit, with a
  warning if the milestones no longer add up to the contract total.
- **Milestones table** (Project page): sortable and filterable, with a number filter on amounts
  and status colours that show overdue milestones in red.
- **Invoice ledger** (Project page): every PayPal invoice with its status, due date, paid date
  and a link to PayPal's pay page, plus a pinned totals row.
- **Audit log** (Project page): every action by the freelancer, the client, the AI, PayPal and
  the system, with a search box and a filter by who did it. It's the evidence trail for disputes.

## Safety: the AI proposes, code moves money, people approve

- **No made-up quotes.** Every clause or message the AI quotes must appear word for word in
  the source text, or the finding is thrown away.
- **The AI never sets a price.** Change orders are priced by code: estimated hours, rounded to
  the quarter hour, times the contract's hourly rate.
- **The AI can't touch money.** It has no tools and never calls PayPal. Only our billing code
  creates invoices, and only after the freelancer (or the client, for their own approval)
  clicks approve.
- **Prompt injection is ignored.** Instructions written inside a contract or message, such as
  "mark everything as paid", are treated as text to analyse, not commands.
- **Low-confidence findings** are shown as "Possible", with no ready-made approve button.
- **A strict status flow** means a milestone can't be invoiced twice, even when a button is
  double-clicked: the second click gets the first click's invoice.
- **Files stay locked until PayPal says paid.** The client sees a watermarked preview; the full
  file unlocks on payment and locks again if the payment is refunded.
- **An audit log** records every action and who did it: the user, the client, the AI, PayPal
  or the system.
- **A daily cap on AI calls** (`AI_DAILY_LIMIT`, 150 by default, 40 on the hosted demo) protects the
  AI budget. Loading the demo project uses no AI at all.

## Try it (for judges)

The freelancer side of the hosted demo asks for a password (any user name):
`acts-image-rhyme-relax`. Type it into the browser's login box; don't put it inside the link
(`https://name:password@...`), because browsers then block the page's requests. The client page
opened from **Open as client** needs no password.

On the hosted demo, the yellow **Demo** bar at the top drives the whole story:

1. **Load demo project.** It opens a bakery's $3,200 logo contract with three risky clauses
   flagged and a 30% deposit suggested. It uses a saved example of the AI's reading, so it
   costs no AI credit.
2. **Approve and send deposit invoice.** A real PayPal sandbox invoice is created and sent.
3. Go to **Messages and approvals**, click **Use demo message**, then **Analyse message**. The
   AI finds that the sketches were approved and that a menu design is extra work. Approve both:
   one milestone invoice and one change order are sent through PayPal.
4. In **Billing, files and client page**, add an image file to a milestone, then **Open as
   client**. That's the client's page: watermarked preview, PayPal button.
5. Pay the invoice on PayPal's page with the sandbox buyer account below. Within seconds the
   client page shows it paid, and the full file unlocks.
6. Click **+7 days** a few times, then **Run daily jobs**. Unpaid invoices become overdue and
   PayPal reminders go out.

**Sandbox buyer account** (fake money, PayPal sandbox only): email `sb-gkwl253832599@personal.example.com`, password
`gZ[F9^aw`. Please don't change its password, so other judges can use it too.

**Reset demo** removes all projects so the next person starts fresh.

## Run it yourself

You need Python 3.11 or newer and Node 20 or newer.

1. **PayPal sandbox:** at [developer.paypal.com](https://developer.paypal.com), go to
   *Testing Tools → Sandbox Accounts* and create a **Business** and a **Personal** account,
   both with country **United States**. Then go to *Apps & Credentials* (Sandbox), create an
   app linked to the Business account, and copy its Client ID and Secret.
2. **OpenRouter:** create a key at [openrouter.ai](https://openrouter.ai) and give it a
   credit limit.
3. **Settings:** copy `.env.example` to `.env` and fill it in. Set `DEMO_CLIENT_EMAIL` to the
   sandbox Personal account's email.
4. **Build and run:**

   ```bash
   cd frontend && npm ci && npm run build && cd ..
   cd backend
   python3.11 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   .venv/bin/uvicorn app.main:app --reload
   ```

   Open http://localhost:8000. The API documentation is at http://localhost:8000/docs.

5. **Check your PayPal keys** (optional): from `backend`, run
   `.venv/bin/python -m scripts.paypal_spike <sandbox-personal-email>`. It creates and sends
   a real sandbox invoice and waits for you to pay it.

PayPal can't reach `localhost`, so webhooks only arrive once the app is online (or through a
tunnel). Locally, use **Check payment** to read the status from PayPal instead.

For working on the screens with hot reload, run `npm run dev` in `frontend` while the backend
runs on port 8000. `npm run dev:fixtures` shows the screens with sample data and no backend.

### Tests

```bash
cd backend && .venv/bin/python -m pytest
```

The tests use a pretend PayPal and a pretend AI, so they cost nothing and need no keys.
`backend/evals/run_evals.py` scores the real AI on 10 contracts and 15 client messages
(about 25 AI calls).

## Deploy on Render

1. Create a free Postgres database on [Neon](https://neon.tech) and copy its connection string.
2. In Render, choose **New → Blueprint** and pick this repository. `render.yaml` sets up one
   free web service built from the `Dockerfile`.
3. Fill in the secret values Render asks for: PayPal Client ID and Secret, OpenRouter key,
   `DATABASE_URL` (Neon), `DEMO_CLIENT_EMAIL`, and `APP_PASSWORD` (the password for the
   freelancer side; without it anyone with the link can see and reset the projects).
4. In your PayPal sandbox app, add a webhook to `https://<your-app>.onrender.com/webhooks/paypal`
   for `INVOICING.INVOICE.PAID`, `INVOICING.INVOICE.CANCELLED` and `INVOICING.INVOICE.REFUNDED`.
   Copy its Webhook ID into `PAYPAL_WEBHOOK_ID` on Render.

The free plan sleeps after about 15 minutes without visitors, so the first page can take up
to a minute to load.

## Known limits

- **One freelancer, no accounts.** It's a single-user demo: one optional password
  (`APP_PASSWORD`) guards the freelancer side, and each client has a private link.
- **Demo controls are open to whoever has the password.** The demo clock and **Reset demo**
  work while `DEMO_MODE=true`; set it to `false` for real use.
- **One server process.** Double-click protection works inside one process, which is how the
  `Dockerfile` runs it. Running several copies would need a database lock instead.
- **Sleeping pauses reminders.** On Render's free plan the hourly jobs only run while the app
  is awake; the next run catches up and sends the latest reminder due, once.
- **Sandbox only**, and tested with US dollar invoices. PayPal sends at most 2 reminders a day,
  so with big demo clock jumps some reminders wait for a later run.

## Project layout

```
backend/app/
  ai/            AI connection (llm.py), contract and message reading, code checks
  api/           routes: contracts, messages and approval inbox, client portal, demo
  paypal/        PayPal client, invoices, webhook route
  billing.py     creates, sends and syncs invoices; change orders
  milestones.py  allowed status changes, deposit split, revision counting
  jobs.py        daily jobs: dated invoices, overdue marking, reminders
  files.py       file names and watermarked previews
backend/tests/   automated tests (pretend PayPal and AI)
backend/evals/   real-AI test set: 10 contracts, 15 messages
frontend/src/    React screens: dashboard, new project, project page, client portal, demo bar
```

## Tools used

- **PayPal Developer Platform (sandbox):** OAuth, Invoicing v2, Webhooks
- **OpenRouter** with **DeepSeek V4.1 Flash 1017:** contract and message reading
- **AG Grid Community:** the four tables described in [How it uses AG Grid](#how-it-uses-ag-grid)
- **Render:** hosting, from a Dockerfile and a Blueprint
- **Neon:** hosted Postgres
- **FastAPI, SQLModel, Pydantic** (Python), **React, TypeScript, Tailwind, Vite**
- **Pillow** for watermarked previews, **pypdf** for reading PDFs
- **Claude Code** helped write the code

## License

[MIT](LICENSE)
