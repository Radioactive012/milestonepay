# Team tasks and schedule

Deadline: Fri 13 Nov 2026, 01:30 IST. Submission target: Thu 12 Nov, 20:00 IST.
Code freeze: Thu 12 Nov, 12:00 IST.

**Person A** (Vinayak): PayPal, data, deploy.
**Person B** (Avirup): AI, UI, story.
Roles can be swapped. Whoever owns an area decides inside it. Anything that changes
a database table or an API route needs both people.

## Notes for each other

Newest at the top. One line per push: who, what changed, anything the other must do.

- Vinayak: README now has the hosted link and the judge logins (app password, sandbox buyer),
  as the rules require for a password-protected demo. Hosted AI cap lowered to 40/day in
  `render.yaml`. **Avirup: the rules say the video must be public on YouTube** ("must be uploaded
  to and made publicly visible on YouTube"), so the README line is back to a YouTube link; please
  put the YouTube link there and on the Devpost form. No third-party logos or copyrighted music.

- Vinayak: the deposit-failure message now says where the retry is: "open the project (Messages and
  approvals) and click Send invoice now on the deposit, in the Billing, files and client page
  section". Avirup: if you want, a Send invoice now button in NewProject's approved state would be
  even easier. The PayPal 403 is the sandbox app's Invoicing feature; Vinayak is switching it on.

- Vinayak: `ContractReader` raises `AIError("Couldn't read this contract. Try again.")` when the
  reading is completely empty (no milestones, risks or questions), as Avirup asked. Slightly
  narrower than "no milestones": a vague contract (like eval c03) may have no clear milestones
  but still has risks and questions worth showing, so it isn't refused. Nothing is saved on error.

- Vinayak: README has a new "How it uses AG Grid" section (your four tables), for the AG Grid
  sponsor prize. Avirup: worth 10 seconds in the video: edit a milestone amount (Total updates)
  and filter the audit log; and a line in the Devpost text.

- Vinayak: `temperature: 0` on every AI call in `ask_json` (Avirup's request, for consistent
  evals and demo; DeepSeek on OpenRouter supports it). The one retry now tells the AI what was
  wrong with its first answer, since at temperature 0 a plain repeat gets the same answer.

- Vinayak: tests now ignore `.env` and real keys completely (`MILESTONEPAY_ENV_FILE=""` set in
  `tests/conftest.py`), so a filled-in `.env` can't change results or spend AI credit.

- Vinayak: PayPal checks against the docs, before real keys: webhook check sends PayPal the
  event exactly as received; create-invoice accepts every reply shape; PayPal's 2-reminders-a-day
  limit gets a plain message; stray spaces in `.env` values are ignored. Confirmed on OpenRouter:
  our DeepSeek model supports strict JSON answers and image input (~$0.001 per contract).

- Vinayak: **full test pass done** (228 tests, also all passing on real Postgres 16). Bugs fixed:
  - Double clicks made two PayPal invoices / two deposits / two change orders. Now one request
    at a time per item (`billing.one_at_a_time`). A suggestion becomes at most one change order.
  - Refunds re-lock the client's files; late PAID events can't undo a refund.
  - Milestones can't be edited after the contract is approved (`PATCH /api/milestones` → 409).
  - **The freelancer side had no password**, so a client could download unpaid files through
    `/api/files/<id>`. New optional `APP_PASSWORD` (`backend/app/access.py`): the browser asks
    for it everywhere except the client page, PayPal webhook and `/health`. Off when empty.
  - A fresh clone crashed on start (`DATABASE_URL=` empty in `.env`); empty settings now mean
    "use the default".
  - Browsers kept an old copy of the page after a deploy; the page is now always rechecked.
  - Client page: messages scroll into view; a dated milestone can be approved once.
  - Shared files touched (small): `api/contracts.py`, `main.py` (one line), `config.py`,
    `tests/conftest.py` (tests ignore your own `.env`; `TEST_DATABASE_URL` runs them on Postgres).
  - **Avirup, found in your files (not changed, your call):**
    1. `NewProject.tsx` `approve()`: if PayPal refuses the deposit, the contract *is* approved
       but the page goes back to "review" and the message is at the top, out of view. Clicking
       Approve again says "already approved". Suggest: on error, `readContract` again and, if
       its status is `active`, show the approved state with the error next to it.
    2. `ProjectPage.tsx`: errors (for example "add your OpenRouter key" or the AI daily limit)
       show at the very top while the button is far below, so Analyse looks like it did nothing.
       `PortalPage.tsx` now uses a ref + `scrollIntoView` for this; the same works for you.
    3. Dashboard lists only approved projects, so a draft you leave can't be found again.
    4. `api/messages.py`: PayPal errors show only the code, e.g. "(401)"; `paypal_reason(error)`
       from `app.paypal.client` gives the reason. Small: the milestone grid refuses bad amounts
       silently; contract upload of a wrong file type answers 502 instead of 422.
    5. `npm audit` flags esbuild/vite (dev server only; nothing that ships). Fix needs a Vite
       major upgrade, so probably leave it until after the deadline.

- Vinayak: **Person A's part is complete** (code side). New:
  - Client page at `/portal/<link>` (`frontend/src/pages/portal/PortalPage.tsx`) and a
    "Billing, files and client page" panel on the project page (client link with copy,
    file upload, Send invoice now, Check payment).
  - Yellow demo bar (`frontend/src/pages/demo/DemoBar.tsx`): load demo project (saved AI
    reading, no credit), +7 days, back to today, run daily jobs, reset demo.
  - One website: the backend serves `frontend/dist` (`backend/app/frontend.py`).
  - Daily cap on real AI calls, `AI_DAILY_LIMIT` (default 150), enforced inside `app.ai.llm`.
  - `Dockerfile`, `.dockerignore`, `render.yaml` for Render. New README with a judge walkthrough.
  - PayPal errors now say why (for example "keys are missing"), not just the code.
  - **Avirup, heads-up on your files** (small additions, please check):
    `frontend/src/main.tsx` (shows the client page for `/portal/...` links),
    `frontend/src/App.tsx` (demo bar under the nav; opens a just-loaded demo draft),
    `frontend/src/pages/ProjectPage.tsx` (the billing panel under the milestones grid),
    `frontend/src/pages/NewProject.tsx` (new optional `draftId` prop to open a saved draft).
  - After pulling: delete `backend/milestonepay.db` (new columns), `pip install -r requirements.txt`.

- Avirup: added `backend/app/api/messages.py` (message analysis and the approval inbox):
  `POST /api/messages`, `GET /api/messages`, `GET /api/suggestions`, and `approve` and `dismiss`
  for a suggestion. They call your `invoice_milestone`, `approve_change_order` and
  `record_revision`. Heads-up on a shared file: one line added to `backend/app/main.py` to
  include the router. `ai/messages.py` now uses your `round_to_quarter_hour`. Also in
  pull request #1: the new project page (`frontend/`) and the evals (`backend/evals/`).
  Merged main into b-frontend: `ai/messages.py` now uses `get_llm().ask_json` and `AIError`.

- Vinayak: **the AI now runs on OpenRouter with DeepSeek V4.1 Flash 1017**, not Anthropic.
  The `anthropic` package is gone. Every AI call goes through `app.ai.llm`:
  `get_llm().ask_json(system=..., content=..., output=YourPydanticModel)` returns a checked
  answer or raises `AIError` with a readable message. Settings are `OPENROUTER_API_KEY` and
  `AI_MODEL` (the old `ANTHROPIC_*` settings no longer exist). PDFs are read locally for free.
  Avirup: please switch `messages.py` to `ask_json` and catch `AIError` before merging PR #1,
  then `pip install -r requirements.txt`. Read "Saving AI credit" in `CLAUDE.md`: we have about $2.

- Vinayak: reminders and demo clock are on main. Daily jobs (`backend/app/jobs.py`) send
  dated milestones' invoices 7 days early, mark late invoices overdue, and send PayPal
  reminders at -3, 0, +3, +7 and +14 days (one per stage; a jump sends only the latest).
  They run hourly and on demand. Demo routes: `GET/POST /api/demo/clock`
  (`{"offset_days": 7}`), `POST /api/demo/run-jobs`. Invoices now show `reminders`.
  Avirup: for dates, use `clock.today(session)`, not `date.today()`. Delete
  `backend/milestonepay.db` after pulling (new tables). Reminder text is a template for
  now; an AI-written version could go in `reminder_text()` later if there's time.

- Vinayak: client portal backend is on main (`backend/app/api/portal.py`). Routes:
  `POST /api/milestones/{id}/files` (upload), `GET /api/files/{id}` (freelancer download),
  `GET /api/portal/{token}` (client view), `POST /api/portal/{token}/milestones/{id}/approve`
  (client approves; event milestones get invoiced), `GET /api/portal/{token}/files/{id}/preview`
  (watermarked image), `GET /api/portal/{token}/files/{id}` (402 until paid).
  `GET /api/contracts/{id}` now lists `files` per milestone. Delete `backend/milestonepay.db`
  after pulling (new `deliverable` table) and run `pip install -r requirements.txt` (Pillow).
  Also fixed: missing Anthropic or PayPal keys now give a clear message instead of a crash.
  Avirup: `ClaudeMessageAI` likely has the same missing-key crash; see `ClaudeContractAI.__init__`.

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
- Message, suggestion and change order tables; hourly rate; change orders billed as
  their own milestone; revision counting
- Client portal backend: private link per contract, client approval, file upload,
  watermarked previews, downloads locked until the PayPal invoice is paid
- Clear errors when AI or PayPal keys are missing
- AI runs on OpenRouter (DeepSeek V4.1 Flash 1017) through one shared connection, `app.ai.llm`
- Daily jobs: dated invoices, overdue marking, PayPal reminders; demo clock and run-jobs routes
- 131 passing tests, all with a pretend PayPal and a pretend AI
- Client page, billing panel, demo bar, one-website serving, AI daily cap, Render files, README

## Not done yet

- Not yet run against real PayPal sandbox or the real AI (needs keys in `.env`)
- Deploy to Render + Neon (needs Vinayak's accounts), first real PayPal and AI run (needs keys),
  demo video and Devpost text
