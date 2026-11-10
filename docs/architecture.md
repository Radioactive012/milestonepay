# Architecture

How MilestonePay fits together. The AI only proposes; code checks it, people approve, and only the billing code talks to PayPal.

```mermaid
flowchart LR
  F["Freelancer<br/>(React app)"]
  C["Client<br/>(private page)"]
  subgraph API["FastAPI backend"]
    direction TB
    R["Routes<br/>contracts, messages, portal"]
    AI["AI reader<br/>ask_json + strict schema"]
    G["Code checks<br/>quote check, price = hours x rate,<br/>confidence cutoff"]
    B["Billing and status flow<br/>invoices, change orders, audit log"]
    J["Daily jobs<br/>early invoices, overdue, reminders"]
  end
  DB[("Database<br/>SQLite / Postgres")]
  LLM["OpenRouter<br/>DeepSeek V4.1 Flash"]
  PP["PayPal sandbox<br/>Invoicing v2, Webhooks"]

  F -->|"paste contract or client message"| R
  R --> AI
  AI <-->|"JSON answer"| LLM
  AI --> G
  G -->|"proposals only"| R
  F -->|"approve"| R
  R --> B
  B <--> DB
  B -->|"create, send, remind"| PP
  PP -->|"signed paid / refunded events"| B
  C -->|"view, approve, pay"| R
  J --> B
```

## Reading the diagram

- **The AI never touches money.** Its answer goes to the code checks (every quote must appear in the source text, the price is hours times the hourly rate, low confidence means "possible") and comes back as a proposal.
- **Only approval moves money.** When the freelancer approves, the billing code creates the PayPal invoice and writes an audit entry.
- **PayPal tells us when it is paid.** Webhook events are signature-checked, and a paid invoice unlocks the client's files.
- **Daily jobs** invoice dated milestones early, mark late invoices overdue and send reminders.
