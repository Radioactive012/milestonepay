import type { Contract } from "./types";

// The demo contract (Harbor Lane Bakery) as the API returns it. Used with `npm run dev:fixtures`
// so the UI can be built and shown without the backend or an Anthropic key.
export const DEMO_CONTRACT_TEXT = `BRAND IDENTITY CONTRACT
Meera Iyer (the Freelancer) will create a rebrand for Harbor Lane Bakery (the Client) for a total of USD 3,200.
Payment schedule: USD 800 when sketches are approved; USD 1,400 for the final logo; USD 1,000 for the brand kit.
Payment is due upon client satisfaction. The Client may request unlimited revisions until fully happy.
All rights in the work transfer to the Client on delivery. Invoices are payable within 30 days.`;

export const fixtureContract = (): Contract => ({
  id: 1,
  client_name: "Harbor Lane Bakery",
  client_email: "owner@harborlane.example",
  currency: "USD",
  stated_total: "3200.00",
  milestone_total: "3200.00",
  payment_terms_days: 30,
  hourly_rate: "40.00",
  status: "draft",
  portal_token: null,
  deposit_pct_suggested: 30,
  deposit_rationale: "Three high-severity risks and most of the payment comes at the end, so ask for 30% up front.",
  warnings: [],
  ambiguities: ["It is not stated what counts as the Client being 'fully happy'."],
  risks: [
    {
      clause_quote: "Payment is due upon client satisfaction.",
      category: "vague_acceptance",
      severity: "high",
      why_it_matters: "The client can delay payment indefinitely by saying they are not satisfied.",
      suggested_rewrite: "Payment is due within 14 days of delivery of each milestone unless the Client reports a specific defect in writing within 5 days.",
    },
    {
      clause_quote: "The Client may request unlimited revisions until fully happy.",
      category: "unlimited_revisions",
      severity: "high",
      why_it_matters: "Unlimited revisions turn a fixed fee into unpaid work.",
      suggested_rewrite: "Each milestone includes two rounds of revisions. Further rounds are billed at USD 40 per hour.",
    },
    {
      clause_quote: "All rights in the work transfer to the Client on delivery.",
      category: "ip_before_payment",
      severity: "high",
      why_it_matters: "The client owns the work before paying for it.",
      suggested_rewrite: "Rights in the work transfer to the Client only when all invoices are paid in full.",
    },
  ],
  milestones: [
    { id: 1, position: 1, title: "Sketches", amount: "800.00", trigger: "event", trigger_description: "When sketches are approved", due_date: null, revision_limit: 2, revisions_used: 0, is_deposit: false, status: "draft", invoice: null },
    { id: 2, position: 2, title: "Final logo", amount: "1400.00", trigger: "event", trigger_description: "On delivery of the final logo", due_date: null, revision_limit: 2, revisions_used: 0, is_deposit: false, status: "draft", invoice: null },
    { id: 3, position: 3, title: "Brand kit", amount: "1000.00", trigger: "event", trigger_description: "On delivery of the brand kit", due_date: null, revision_limit: 2, revisions_used: 0, is_deposit: false, status: "draft", invoice: null },
  ],
  change_orders: [],
  audit: [{ actor: "ai", action: "contract_analysed", details: { milestones: 3, risks: 3 }, at: new Date().toISOString() }],
});
