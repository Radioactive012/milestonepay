# Project status and team notes

Built for the PayPal AI Hackathon. Deadline: Fri 13 Nov 2026, 01:30 IST.

- **Person A**: PayPal, database, money flow, client page, hosting.
- **Person B**: AI prompts, web screens, test contracts and messages, demo video.

Whoever owns an area decides inside it. Anything that changes a database table or an API
route needs both people. `CLAUDE.md` has the full list of who owns which files.

## Notes for each other

Newest at the top. One line per push: who (Person A or B), what changed, anything the other must do.

## What's built

- **Contract reading**: paste text, upload a PDF or a photo. The AI lists milestones, flags risky
  clauses with a fairer rewrite, and suggests a deposit. Code checks drop any clause that isn't
  quoted word for word and warn when amounts don't add up.
- **Approval and deposit**: the freelancer edits the milestones in a grid and approves; the
  deposit invoice goes out through PayPal.
- **Client messages**: pasted by the freelancer or written by the client on their own page. The AI
  proposes milestone invoices, change orders (hours x hourly rate) and revision counts; each waits
  in an approval inbox.
- **PayPal (sandbox)**: Invoicing v2 (create, send, remind, read status), signed webhooks for
  paid, cancelled and refunded, and an hourly check of unpaid invoices in case a webhook is missed.
- **Client page**: private link per project with milestones, PayPal pay buttons, watermarked
  previews, and files that unlock when the invoice is paid (and lock again after a refund).
- **Daily jobs**: dated invoices a week early, overdue marking, reminders at -3, 0, +3, +7 and
  +14 days. A demo clock lets judges jump ahead in time.
- **Evidence pack**: one printable page per project for payment disputes.
- **Payment timeline** (Bryntum Gantt) and tables (AG Grid) on the freelancer side.
- **Safety**: the AI never calls PayPal or sets a final amount; every action is in the audit log;
  double clicks can't bill twice; a daily cap limits real AI calls; an optional password guards
  the freelancer side.
- **Hosting**: one Docker container on Render, Postgres on Neon.
- **Tests**: the whole backend is covered by automated tests that use a pretend PayPal and a
  pretend AI, so they cost nothing to run.

## Left before submitting

- Public YouTube video (under 3 minutes) and its link in `README.md`
- Devpost text and testing instructions
- Reset the hosted demo so judges start clean
