import type { Contract, Milestone } from "../types";

// Sums are done in whole cents, so 0.1 + 0.2 style rounding errors can't show up on screen.
const cents = (amount: string | null) => Math.round(Number(amount ?? 0) * 100);

export interface Totals {
  received: number;
  expected: number;
  overdue: number;
  waiting: number;
  notInvoiced: number;
}

const REFUNDED = new Set(["REFUNDED", "MARKED_AS_REFUNDED"]);

export const todayIso = () => new Date().toISOString().slice(0, 10);

export function isOverdue(m: Milestone, today = todayIso()): boolean {
  if (m.status === "overdue") return true;
  const inv = m.invoice;
  return m.status === "invoiced" && !!inv && inv.status === "SENT" && !!inv.due_date && inv.due_date < today;
}

/** Everything is in money units (not cents). "expected" is all money still to come in, overdue included. */
export function totalsFor(contracts: Contract[], today = todayIso()): Totals {
  const t = { received: 0, expected: 0, overdue: 0, waiting: 0, notInvoiced: 0 };
  for (const c of contracts) {
    for (const m of c.milestones) {
      const value = cents(m.amount);
      // a refunded payment went back to the client, so it is neither received nor still expected
      if (m.status === "paid" && REFUNDED.has(m.invoice?.status ?? "")) continue;
      if (m.status === "paid") t.received += value;
      else if (m.status === "cancelled") continue;
      else if (m.status === "draft" && !m.is_deposit && m.trigger !== "change_order") continue; // not approved yet
      else {
        t.expected += value;
        if (isOverdue(m, today)) t.overdue += value;
        else if (m.status === "invoiced") t.waiting += value;
        else t.notInvoiced += value;
      }
    }
  }
  return {
    received: t.received / 100,
    expected: t.expected / 100,
    overdue: t.overdue / 100,
    waiting: t.waiting / 100,
    notInvoiced: t.notInvoiced / 100,
  };
}
