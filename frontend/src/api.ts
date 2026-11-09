import { fakeAnalyse } from "./fixtureMessages";
import { fixtureContract } from "./fixtures";
import type {
  ApproveEdits, ApproveResult, Contract, ContractSummary, MilestoneChanges,
  PostMessageResult, Suggestion, ThreadMessage,
} from "./types";

export const USE_FIXTURES = import.meta.env.VITE_USE_FIXTURES === "1";

export class ApiError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new ApiError("Couldn't reach the server. Is the backend running on port 8000?");
  }
  if (!response.ok) {
    let detail = `Something went wrong (${response.status}).`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) detail = body.detail.map((d: { msg: string }) => d.msg).join(". ");
    } catch {
      /* keep the generic message */
    }
    throw new ApiError(detail);
  }
  return response.json() as Promise<T>;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

// --- fixture mode: in-memory data so every screen works without the backend ---
let demo: Contract | null = null;
let fxMessages: ThreadMessage[] = [];
let fxSuggestions: Suggestion[] = [];
let nextId = 1;
const pause = (ms = 500) => new Promise((resolve) => setTimeout(resolve, ms));
const quarter = (hours: number) => Math.max(Math.round(hours * 4) / 4, 0.25);
const now = () => new Date().toISOString();
const inDays = (days: number) => new Date(Date.now() + days * 86_400_000).toISOString().slice(0, 10);
const fxAudit = (c: Contract, actor: string, action: string, details: Record<string, unknown> = {}) =>
  c.audit.push({ actor, action, details, at: now() });

function approveDemo(c: Contract, depositPct: number) {
  const total = c.milestones.reduce((s, m) => s + Number(m.amount ?? 0), 0);
  const deposit = Math.round(total * depositPct) / 100;
  // Like the real backend: the deposit comes out of the milestones, so the total stays the same.
  let left = total - deposit;
  c.milestones.forEach((m, i) => {
    const last = i === c.milestones.length - 1;
    const reduced = last ? left : Math.round(Number(m.amount ?? 0) * (100 - depositPct)) / 100;
    m.amount = reduced.toFixed(2);
    left -= reduced;
  });
  c.status = "active";
  c.milestones.forEach((m) => (m.status = m.trigger === "date" ? "scheduled" : "awaiting_trigger"));
  if (depositPct > 0) {
    c.milestones.unshift({
      id: 99, position: 0, title: `Deposit (${depositPct}%)`, amount: deposit.toFixed(2), trigger: "approval",
      trigger_description: "Paid before work starts", due_date: null, revision_limit: null, revisions_used: 0,
      is_deposit: true, status: "invoiced",
      invoice: { id: 1, number: "MP-2026-0001", paypal_invoice_id: "INV2-DEMO", amount: deposit.toFixed(2), status: "SENT",
        payer_url: "https://www.sandbox.paypal.com/", due_date: inDays(30), paid_at: null },
    });
    fxAudit(c, "user", "invoice_sent", { number: "MP-2026-0001", amount: deposit.toFixed(2) });
  }
  fxAudit(c, "user", "contract_approved", { deposit_pct: depositPct });
}

/** The demo contract, approved with no deposit if nobody went through the new project page yet. */
function activeDemo(): Contract {
  if (!demo) demo = fixtureContract();
  if (demo.status !== "active") approveDemo(demo, 0);
  return demo;
}

function fxInvoice(amount: string, id: number) {
  return { id, number: `MP-2026-${String(id).padStart(4, "0")}`, paypal_invoice_id: `INV2-DEMO-${id}`, amount, status: "SENT",
    payer_url: "https://www.sandbox.paypal.com/", due_date: inDays(30), paid_at: null };
}

// --- contracts ---
export async function createContract(input: {
  clientEmail: string;
  clientName?: string;
  hourlyRate?: number;
  text?: string;
  file?: File | null;
}): Promise<Contract> {
  if (USE_FIXTURES) {
    await pause(600);
    demo = fixtureContract();
    if (input.hourlyRate) demo.hourly_rate = input.hourlyRate.toFixed(2);
    fxMessages = [];
    fxSuggestions = [];
    return structuredClone(demo);
  }
  const form = new FormData();
  form.append("client_email", input.clientEmail);
  if (input.clientName) form.append("client_name", input.clientName);
  if (input.hourlyRate) form.append("hourly_rate", String(input.hourlyRate));
  if (input.text) form.append("text", input.text);
  if (input.file) form.append("file", input.file);
  return request<Contract>("/api/contracts", { method: "POST", body: form });
}

export async function listContracts(): Promise<ContractSummary[]> {
  if (USE_FIXTURES) {
    const c = activeDemo();
    return [{ id: c.id, client_name: c.client_name, currency: c.currency, status: c.status, created_at: now() }];
  }
  return request<ContractSummary[]>("/api/contracts");
}

export async function readContract(id: number): Promise<Contract> {
  if (USE_FIXTURES) return structuredClone(activeDemo());
  return request<Contract>(`/api/contracts/${id}`);
}

export async function updateHourlyRate(id: number, rate: number): Promise<Contract> {
  if (USE_FIXTURES) {
    activeDemo().hourly_rate = rate.toFixed(2);
    fxAudit(demo!, "user", "hourly_rate_changed", { hourly_rate: rate.toFixed(2) });
    return structuredClone(demo!);
  }
  return request<Contract>(`/api/contracts/${id}`, json("PATCH", { hourly_rate: rate }));
}

export async function updateMilestone(id: number, changes: MilestoneChanges): Promise<Contract> {
  if (USE_FIXTURES && demo) {
    const m = demo.milestones.find((x) => x.id === id)!;
    if (changes.title !== undefined) m.title = changes.title;
    if (changes.amount !== undefined) m.amount = changes.amount.toFixed(2);
    if (changes.trigger !== undefined) m.trigger = changes.trigger;
    if (changes.due_date !== undefined) m.due_date = changes.due_date;
    if (changes.trigger_description !== undefined) m.trigger_description = changes.trigger_description;
    if (m.trigger === "event") m.due_date = null;
    const total = demo.milestones.reduce((sum, x) => sum + Number(x.amount ?? 0), 0);
    demo.milestone_total = total.toFixed(2);
    return structuredClone(demo);
  }
  return request<Contract>(`/api/milestones/${id}`, json("PATCH", changes));
}

export async function approveContract(id: number, depositPct: number): Promise<Contract> {
  if (USE_FIXTURES && demo) {
    await pause(600);
    approveDemo(demo, depositPct);
    return structuredClone(demo);
  }
  return request<Contract>(`/api/contracts/${id}/approve`, json("POST", { deposit_pct: depositPct }));
}

export async function refreshInvoice(invoiceId: number): Promise<Contract> {
  if (USE_FIXTURES && demo) {
    const m = demo.milestones.find((x) => x.invoice?.id === invoiceId)!;
    m.invoice!.status = "PAID";
    m.invoice!.paid_at = now();
    m.status = "paid";
    fxAudit(demo, "paypal", "invoice_paid", { number: m.invoice!.number, amount: m.invoice!.amount });
    return structuredClone(demo);
  }
  return request<Contract>(`/api/invoices/${invoiceId}/refresh`, { method: "POST" });
}

// --- client messages and the approval inbox ---
export async function postMessage(contractId: number, body: string): Promise<PostMessageResult> {
  if (USE_FIXTURES) {
    await pause(900);
    const c = activeDemo();
    const { drafts, dropped } = fakeAnalyse(body, c);
    const made: Suggestion[] = drafts.map((d) => ({
      id: nextId++, contract_id: c.id, message_id: null, milestone_id: d.milestoneId, type: d.type, payload: d.payload,
      evidence_quote: d.quote, confidence: d.confidence, possible: d.confidence < 0.6, status: "pending",
      message_body: body, created_at: now(),
    }));
    const message: ThreadMessage = {
      id: nextId++, contract_id: c.id, sender: "pasted", body, analysis: { dropped },
      tags: made.map((s) => ({ type: s.type, status: s.status })), created_at: now(),
    };
    made.forEach((s) => (s.message_id = message.id));
    fxMessages.push(message);
    fxSuggestions.push(...made);
    fxAudit(c, "ai", "message_analysed", { message_id: message.id, suggestions: made.length, dropped: dropped.length });
    return structuredClone({ message, suggestions: made, dropped });
  }
  return request<PostMessageResult>("/api/messages", json("POST", { contract_id: contractId, body }));
}

export async function listMessages(contractId: number): Promise<ThreadMessage[]> {
  if (USE_FIXTURES) {
    return structuredClone(
      fxMessages.map((m) => ({ ...m, tags: fxSuggestions.filter((s) => s.message_id === m.id).map((s) => ({ type: s.type, status: s.status })) })),
    );
  }
  return request<ThreadMessage[]>(`/api/messages?contract_id=${contractId}`);
}

export async function listSuggestions(contractId: number | null, status = "pending"): Promise<Suggestion[]> {
  if (USE_FIXTURES) {
    // newest message first; inside one message, the order the AI found them
    const found = fxSuggestions.filter((s) => s.status === status);
    found.sort((a, b) => (b.message_id ?? 0) - (a.message_id ?? 0) || a.id - b.id);
    return structuredClone(found);
  }
  return request<Suggestion[]>(`/api/suggestions?status=${status}${contractId === null ? "" : `&contract_id=${contractId}`}`);
}

export async function dismissSuggestion(id: number): Promise<Suggestion> {
  if (USE_FIXTURES) {
    const s = fxSuggestions.find((x) => x.id === id && x.status === "pending");
    if (!s) throw new ApiError("This suggestion was already handled.");
    s.status = "dismissed";
    fxAudit(activeDemo(), "user", "suggestion_dismissed", { suggestion_id: s.id, type: s.type });
    return structuredClone(s);
  }
  return request<Suggestion>(`/api/suggestions/${id}/dismiss`, { method: "POST" });
}

export async function approveSuggestion(id: number, edits?: ApproveEdits): Promise<ApproveResult> {
  if (USE_FIXTURES) {
    await pause(700);
    const c = activeDemo();
    const s = fxSuggestions.find((x) => x.id === id);
    if (!s || s.status !== "pending") throw new ApiError("This suggestion was already handled.");
    if (s.possible) throw new ApiError("The AI isn't sure about this one. Dismiss it, or handle it by hand.");
    const milestone = c.milestones.find((m) => m.id === s.milestone_id);
    if (s.type === "milestone_reached" && milestone) {
      milestone.status = "invoiced";
      milestone.invoice = fxInvoice(milestone.amount ?? "0.00", nextId++);
      fxAudit(c, "user", "invoice_sent", { number: milestone.invoice.number, amount: milestone.amount });
    } else if (s.type === "scope_creep") {
      const hours = quarter(edits?.hours ?? Number(s.payload.estimated_hours));
      const description = (edits?.description ?? String(s.payload.description)).trim();
      if (!description) throw new ApiError("Describe the extra work.");
      const price = (hours * Number(c.hourly_rate)).toFixed(2);
      const milestoneId = 100 + nextId++;
      c.milestones.push({
        id: milestoneId, position: Math.max(...c.milestones.map((m) => m.position)) + 1,
        title: `Change order: ${description}`, amount: price, trigger: "change_order",
        trigger_description: `${hours.toFixed(2)} h at ${c.currency} ${c.hourly_rate}/h`, due_date: null,
        revision_limit: null, revisions_used: 0, is_deposit: false, status: "invoiced", invoice: fxInvoice(price, nextId++),
      });
      fxAudit(c, "user", "change_order_approved", { description, hours: hours.toFixed(2), price });
      c.change_orders.push({ id: nextId++, description, estimated_hours: hours.toFixed(2), price, milestone_id: milestoneId, suggestion_id: s.id });
    } else if (s.type === "extra_revision" && milestone) {
      milestone.revisions_used += 1;
      fxAudit(c, "user", "revision_counted", { milestone_id: milestone.id, used: milestone.revisions_used });
    }
    s.status = "approved";
    fxAudit(c, "user", "suggestion_approved", { suggestion_id: s.id, type: s.type });
    return structuredClone({ suggestion: s, contract: c });
  }
  return request<ApproveResult>(`/api/suggestions/${id}/approve`, edits ? json("POST", edits) : { method: "POST" });
}
