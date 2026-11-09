import { fixtureContract } from "./fixtures";
import type { Contract, MilestoneChanges } from "./types";

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

// --- fixture mode: an in-memory contract so every screen works without the backend ---
let demo: Contract | null = null;
const pause = () => new Promise((resolve) => setTimeout(resolve, 600));

export async function createContract(input: {
  clientEmail: string;
  clientName?: string;
  text?: string;
  file?: File | null;
}): Promise<Contract> {
  if (USE_FIXTURES) {
    await pause();
    demo = fixtureContract();
    return structuredClone(demo);
  }
  const form = new FormData();
  form.append("client_email", input.clientEmail);
  if (input.clientName) form.append("client_name", input.clientName);
  if (input.text) form.append("text", input.text);
  if (input.file) form.append("file", input.file);
  return request<Contract>("/api/contracts", { method: "POST", body: form });
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
    await pause();
    const total = demo.milestones.reduce((s, m) => s + Number(m.amount ?? 0), 0);
    const deposit = Math.round(total * depositPct) / 100;
    // Like the real backend: the deposit comes out of the milestones, so the total stays the same.
    let left = total - deposit;
    demo.milestones.forEach((m, i) => {
      const last = i === demo.milestones.length - 1;
      const reduced = last ? left : Math.round(Number(m.amount ?? 0) * (100 - depositPct)) / 100;
      m.amount = reduced.toFixed(2);
      left -= reduced;
    });
    demo.status = "active";
    demo.milestones.forEach((m) => (m.status = m.trigger === "date" ? "scheduled" : "awaiting_trigger"));
    if (depositPct > 0) {
      demo.milestones.unshift({
        id: 99, position: 0, title: `Deposit (${depositPct}%)`, amount: deposit.toFixed(2), trigger: "approval",
        trigger_description: "Paid before work starts", due_date: null, revision_limit: null, is_deposit: true, status: "invoiced",
        invoice: { id: 1, number: "MP-2026-0001", paypal_invoice_id: "INV2-DEMO", amount: deposit.toFixed(2), status: "SENT",
          payer_url: "https://www.sandbox.paypal.com/", due_date: null, paid_at: null },
      });
    }
    return structuredClone(demo);
  }
  return request<Contract>(`/api/contracts/${id}/approve`, json("POST", { deposit_pct: depositPct }));
}

export async function refreshInvoice(invoiceId: number): Promise<Contract> {
  if (USE_FIXTURES && demo) {
    const m = demo.milestones.find((x) => x.invoice?.id === invoiceId)!;
    m.invoice!.status = "PAID";
    m.invoice!.paid_at = new Date().toISOString();
    m.status = "paid";
    return structuredClone(demo);
  }
  return request<Contract>(`/api/invoices/${invoiceId}/refresh`, { method: "POST" });
}
