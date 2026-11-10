import { useEffect, useRef, useState } from "react";
import { isOverdue } from "../lib/totals";
import type { Contract, Milestone } from "../types";

// Bryntum Gantt is large (several MB), so it is loaded only when this timeline is on screen.
type GanttInstance = { destroy: () => void };

const DAY = 24 * 60 * 60 * 1000;
const addDays = (iso: string, days: number) => new Date(new Date(iso).getTime() + days * DAY).toISOString().slice(0, 10);

function colour(m: Milestone): string {
  if (m.status === "paid") return "green";
  if (isOverdue(m)) return "red";
  if (m.invoice) return "blue";
  return "gray";
}

/** One row per milestone that has a date: an invoice bar (sent → due), or a diamond for a payment date still to come. */
export function timelineRows(contract: Contract) {
  const money = new Intl.NumberFormat(undefined, { style: "currency", currency: contract.currency || "USD" });
  const rows = [];
  const waiting: Milestone[] = [];
  for (const m of contract.milestones) {
    if (m.status === "cancelled") continue;
    const label = `${m.title} · ${money.format(Number(m.amount ?? 0))}`;
    const due = m.invoice?.due_date;
    if (due) {
      // the invoice period: sent, then due after the contract's payment terms
      const start = addDays(due, -Math.max(contract.payment_terms_days, 1));
      rows.push({ id: m.id, name: label, startDate: start, endDate: due, manuallyScheduled: true, eventColor: colour(m) });
    } else if (m.due_date) {
      rows.push({ id: m.id, name: label, startDate: m.due_date, duration: 0, manuallyScheduled: true, eventColor: colour(m) });
    } else {
      waiting.push(m);
    }
  }
  return { rows, waiting };
}

export default function PaymentTimeline({ contract }: { contract: Contract }) {
  const holder = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const { rows, waiting } = timelineRows(contract);

  useEffect(() => {
    let gantt: GanttInstance | null = null;
    let cancelled = false;
    if (rows.length === 0) {
      setLoading(false);
      return;
    }
    (async () => {
      const [{ Gantt }] = await Promise.all([
        import("@bryntum/gantt-trial"),
        import("@bryntum/gantt-trial/fontawesome/css/fontawesome.css"),
        import("@bryntum/gantt-trial/fontawesome/css/solid.css"),
        import("@bryntum/gantt-trial/gantt.css"),
        import("@bryntum/gantt-trial/stockholm-light.css"),
      ]);
      if (cancelled || !holder.current) return;
      const dates = rows
        .flatMap((r) => [r.startDate, "endDate" in r ? r.endDate : undefined])
        .filter((d): d is string => !!d)
        .sort();
      const first = dates[0] ?? contract.milestones[0]?.due_date ?? new Date().toISOString().slice(0, 10);
      const last = dates[dates.length - 1] ?? first;
      gantt = new Gantt({
        appendTo: holder.current,
        readOnly: true,
        height: Math.min(80 + rows.length * 44, 360),
        startDate: addDays(first, -2),
        endDate: addDays(last, 14),
        viewPreset: "weekAndDayLetter",
        columns: [{ type: "name", text: "Payment", width: 200 }],
        features: { taskMenu: false, cellMenu: false, headerMenu: false, taskEdit: false, dependencies: false, projectLines: false },
        project: { tasks: rows },
      }) as unknown as GanttInstance;
      setLoading(false);
    })().catch(() => {
      if (!cancelled) {
        setError("The timeline couldn't be loaded. The tables below have the same information.");
        setLoading(false);
      }
    });
    return () => {
      cancelled = true;
      gantt?.destroy();
    };
  }, [JSON.stringify(rows)]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-3">
      <p className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
        <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-blue-500" />Invoice sent, waiting</span>
        <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-green-500" />Paid</span>
        <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-red-500" />Overdue</span>
        <span><span className="mr-1 inline-block h-2.5 w-2.5 rotate-45 bg-slate-400" />Payment date to come</span>
      </p>
      {rows.length === 0 ? (
        <p className="rounded-lg border border-dashed border-slate-300 p-4 text-sm text-slate-500">
          Nothing has a date yet. Invoices and dated milestones appear here.
        </p>
      ) : (
        <>
          {loading && <p className="text-sm text-slate-500">Loading the timeline…</p>}
          {error && <p className="text-sm text-amber-800">{error}</p>}
          <div ref={holder} className="overflow-hidden rounded-lg border border-slate-200" />
        </>
      )}
      {waiting.length > 0 && (
        <p className="text-sm text-slate-600">
          Waiting for an event, so not on the timeline yet: {waiting.map((m) => m.title).join(", ")}.
        </p>
      )}
    </div>
  );
}
