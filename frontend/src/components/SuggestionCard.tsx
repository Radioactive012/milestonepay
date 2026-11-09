import { useState } from "react";
import type { ApproveEdits, Contract, Suggestion } from "../types";

interface Props {
  suggestion: Suggestion;
  contract: Contract;
  busy: boolean;
  onApprove: (id: number, edits?: ApproveEdits) => void;
  onDismiss: (id: number) => void;
}

const TITLE: Record<Suggestion["type"], string> = {
  milestone_reached: "Milestone reached: send the invoice",
  scope_creep: "Extra work: send a change order",
  extra_revision: "Revision request",
};

const quarter = (hours: number) => Math.max(Math.round(hours * 4) / 4, 0.25);

export default function SuggestionCard({ suggestion: s, contract, busy, onApprove, onDismiss }: Props) {
  const p = s.payload;
  const [hours, setHours] = useState(String(p.estimated_hours ?? ""));
  const [description, setDescription] = useState(String(p.description ?? ""));
  const money = new Intl.NumberFormat(undefined, { style: "currency", currency: contract.currency || "USD" });

  const hoursNumber = Number(hours);
  const hoursValid = Number.isFinite(hoursNumber) && hoursNumber > 0 && hoursNumber <= 200;
  // A preview only: the server works out the real price from the rounded hours and the contract's rate.
  const previewPrice = hoursValid ? quarter(hoursNumber) * Number(contract.hourly_rate) : null;

  return (
    <li className="space-y-3 rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold">{TITLE[s.type]}</h3>
        {s.possible && (
          <span className="rounded-full border border-amber-300 bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-900">
            Possible
          </span>
        )}
      </div>

      <blockquote className="border-l-4 border-sky-300 pl-3 text-sm italic text-slate-700">“{s.evidence_quote}”</blockquote>

      {s.type === "milestone_reached" && (
        <p className="text-sm text-slate-700">
          The client seems to have approved <strong>{String(p.milestone_title)}</strong>. Approving sends a PayPal invoice for{" "}
          {money.format(Number(p.amount))}.
        </p>
      )}

      {s.type === "scope_creep" && (
        <div className="space-y-2 text-sm text-slate-700">
          <p>{String(p.reason)}</p>
          <p className="text-xs text-slate-500">
            Contract says: “{String(p.contract_clause_quote)}”
          </p>
          <div className="grid gap-3 sm:grid-cols-[1fr_8rem_8rem]">
            <label>
              <span className="mb-1 block text-xs font-medium">What the change order covers</span>
              <input value={description} onChange={(e) => setDescription(e.target.value)} maxLength={200}
                className="w-full rounded-lg border border-slate-300 px-3 py-2" />
            </label>
            <label>
              <span className="mb-1 block text-xs font-medium">Hours (estimate)</span>
              <input value={hours} onChange={(e) => setHours(e.target.value)} inputMode="decimal"
                className="w-full rounded-lg border border-slate-300 px-3 py-2" />
            </label>
            <div>
              <span className="mb-1 block text-xs font-medium">Price</span>
              <p className="rounded-lg bg-slate-100 px-3 py-2 font-semibold">
                {previewPrice === null ? "–" : money.format(previewPrice)}
              </p>
            </div>
          </div>
          <p className="text-xs text-slate-500">
            Hours × {money.format(Number(contract.hourly_rate))} per hour, rounded to quarter hours. The AI only estimates the
            hours; the price is worked out by code.
          </p>
        </div>
      )}

      {s.type === "extra_revision" && (
        <p className="text-sm text-slate-700">
          The client asks for changes to <strong>{String(p.milestone_title)}</strong>. That would be revision round{" "}
          {Number(p.revisions_used) + 1}
          {p.revision_limit !== null && <> of {String(p.revision_limit)} included</>}.
          {p.over_limit && (
            <span className="mt-2 block rounded bg-amber-50 p-2 text-amber-900">
              This goes past the included rounds. Consider quoting it as extra work.
            </span>
          )}
        </p>
      )}

      {s.possible ? (
        <p className="text-sm text-amber-800">The AI isn't sure about this one. Check the message, or dismiss it.</p>
      ) : null}

      <div className="flex flex-wrap gap-3">
        {!s.possible && (
          <button
            disabled={busy || (s.type === "scope_creep" && (!hoursValid || !description.trim()))}
            onClick={() =>
              onApprove(s.id, s.type === "scope_creep" ? { hours: quarter(hoursNumber), description: description.trim() } : undefined)
            }
            className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {s.type === "milestone_reached" && "Approve and send invoice"}
            {s.type === "scope_creep" && "Approve and send change order"}
            {s.type === "extra_revision" && "Count this revision"}
          </button>
        )}
        <button disabled={busy} onClick={() => onDismiss(s.id)}
          className="rounded-lg border border-slate-300 px-4 py-2 text-sm disabled:opacity-50">
          Dismiss
        </button>
      </div>
    </li>
  );
}
