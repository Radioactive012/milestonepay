import { useEffect, useState } from "react";
import { ApiError, USE_FIXTURES, listContracts, listSuggestions, readContract } from "../api";
import { totalsFor } from "../lib/totals";
import type { Contract, ContractSummary } from "../types";

interface Props {
  onOpenProject: (id: number) => void;
  onNewProject: () => void;
  onOpenDraft: (id: number) => void;
  onOpenInbox: () => void;
}

export default function Dashboard({ onOpenProject, onNewProject, onOpenDraft, onOpenInbox }: Props) {
  const [contracts, setContracts] = useState<Contract[] | null>(null);
  const [drafts, setDrafts] = useState<ContractSummary[]>([]);
  const [waiting, setWaiting] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      const all = await listContracts();
      setDrafts(all.filter((c) => c.status === "draft"));
      const summaries = all.filter((c) => c.status === "active");
      setContracts(await Promise.all(summaries.map((c) => readContract(c.id))));
      setWaiting((await listSuggestions(null)).length);
    })().catch((e) => setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again."));
  }, []);

  // Money is grouped per currency, so two currencies are never added together.
  const byCurrency = new Map<string, Contract[]>();
  (contracts ?? []).forEach((c) => byCurrency.set(c.currency, [...(byCurrency.get(c.currency) ?? []), c]));

  return (
    <main className="mx-auto max-w-5xl space-y-6 px-4 py-8">
      <header>
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <p className="text-sm text-slate-600">
          Where your money stands across all projects.
          {USE_FIXTURES && <span className="ml-2 rounded bg-amber-100 px-2 py-0.5 text-amber-900">Fixture mode: no backend needed</span>}
        </p>
      </header>

      {error && <p role="alert" className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-900">{error}</p>}
      {contracts === null && !error && <p className="text-sm text-slate-500">Loading…</p>}

      {contracts !== null && contracts.length === 0 && (
        <section className="rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center">
          <p className="mb-3 text-sm text-slate-600">No approved projects yet. Paste a contract to get started.</p>
          <button onClick={onNewProject} className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white">
            Start a new project
          </button>
        </section>
      )}

      {[...byCurrency.entries()].map(([currency, list]) => {
        const t = totalsFor(list);
        const money = new Intl.NumberFormat(undefined, { style: "currency", currency });
        const tiles = [
          { label: "Expected", value: t.expected, note: "Still to come in, overdue included", style: "border-slate-200" },
          { label: "Received", value: t.received, note: "Paid invoices", style: "border-emerald-300 bg-emerald-50" },
          { label: "Overdue", value: t.overdue, note: "Past the due date", style: t.overdue > 0 ? "border-red-300 bg-red-50" : "border-slate-200" },
        ];
        return (
          <section key={currency} className="space-y-3">
            {byCurrency.size > 1 && <h2 className="text-lg font-semibold">{currency}</h2>}
            <div className="grid gap-4 sm:grid-cols-3">
              {tiles.map((tile) => (
                <div key={tile.label} className={`rounded-xl border bg-white p-4 ${tile.style}`}>
                  <p className="text-sm text-slate-600">{tile.label}</p>
                  <p className="text-2xl font-bold">{money.format(tile.value)}</p>
                  <p className="text-xs text-slate-500">{tile.note}</p>
                </div>
              ))}
            </div>
            <p className="text-sm text-slate-600">
              Of the expected amount, {money.format(t.waiting)} is invoiced and waiting for payment, and{" "}
              {money.format(t.notInvoiced)} isn't invoiced yet.
            </p>
          </section>
        );
      })}

      {drafts.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-lg font-semibold">Drafts waiting for approval</h2>
          <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white">
            {drafts.map((d) => (
              <li key={d.id} className="flex flex-wrap items-center justify-between gap-2 p-4 text-sm">
                <span className="font-medium">{d.client_name} <span className="font-normal text-slate-500">(not approved yet)</span></span>
                <button onClick={() => onOpenDraft(d.id)} className="rounded-lg border border-slate-300 px-3 py-1.5">
                  Continue
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {contracts !== null && contracts.length > 0 && (
        <>
          <section className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-4">
            <p className="text-sm">
              <strong>{waiting}</strong> suggestion{waiting === 1 ? "" : "s"} waiting for your approval
            </p>
            <button onClick={onOpenInbox} className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white">
              Open the approval inbox
            </button>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-semibold">Projects</h2>
            <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white">
              {contracts.map((c) => {
                const t = totalsFor([c]);
                const money = new Intl.NumberFormat(undefined, { style: "currency", currency: c.currency });
                return (
                  <li key={c.id}>
                    <button onClick={() => onOpenProject(c.id)}
                      className="flex w-full flex-wrap items-center justify-between gap-2 p-4 text-left text-sm hover:bg-slate-50">
                      <span className="font-medium">{c.client_name}</span>
                      <span className="text-slate-600">
                        Received {money.format(t.received)} · Expected {money.format(t.expected)}
                        {t.overdue > 0 && <span className="ml-2 rounded-full bg-red-100 px-2 py-0.5 text-xs text-red-800">{money.format(t.overdue)} overdue</span>}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        </>
      )}
    </main>
  );
}
