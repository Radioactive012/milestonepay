import { useCallback, useEffect, useState } from "react";
import {
  ApiError, USE_FIXTURES, approveSuggestion, dismissSuggestion, listContracts, listMessages,
  listSuggestions, postMessage, readContract, updateHourlyRate,
} from "../api";
import MessageThread from "../components/MessageThread";
import SuggestionCard from "../components/SuggestionCard";
import type { ApproveEdits, Contract, ContractSummary, Suggestion, ThreadMessage } from "../types";

const DEMO_MESSAGE = "Sketches approved! Could you also add a matching menu design?";

export default function ProjectPage({ contractId: initialId }: { contractId: number | null }) {
  const [contracts, setContracts] = useState<ContractSummary[] | null>(null);
  const [contractId, setContractId] = useState<number | null>(initialId);
  const [contract, setContract] = useState<Contract | null>(null);
  const [messages, setMessages] = useState<ThreadMessage[]>([]);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [text, setText] = useState("");
  const [rate, setRate] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const fail = (e: unknown) => setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");

  useEffect(() => {
    listContracts()
      .then((all) => {
        const active = all.filter((c) => c.status === "active");
        setContracts(active);
        if (contractId === null && active.length > 0) setContractId(active[0].id);
      })
      .catch(fail);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const reload = useCallback(async (id: number) => {
    const [c, m, s] = await Promise.all([readContract(id), listMessages(id), listSuggestions(id)]);
    setContract(c);
    setRate(Number(c.hourly_rate).toFixed(2));
    setMessages(m);
    setSuggestions(s);
  }, []);

  useEffect(() => {
    if (contractId !== null) reload(contractId).catch(fail);
  }, [contractId, reload]);

  async function run(work: () => Promise<void>) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await work();
    } catch (e) {
      fail(e);
      if (contractId !== null) reload(contractId).catch(() => undefined); // show what really happened
    } finally {
      setBusy(false);
    }
  }

  const addMessage = () =>
    run(async () => {
      if (contractId === null || !text.trim()) return;
      const result = await postMessage(contractId, text.trim());
      setText("");
      await reload(contractId);
      if (result.suggestions.length === 0) setNotice("Nothing in that message needs your action.");
    });

  const approve = (id: number, edits?: ApproveEdits) =>
    run(async () => {
      await approveSuggestion(id, edits);
      if (contractId !== null) await reload(contractId);
      setNotice("Done. The invoice or change was recorded in the audit log.");
    });

  const dismiss = (id: number) =>
    run(async () => {
      await dismissSuggestion(id);
      if (contractId !== null) await reload(contractId);
    });

  const saveRate = () =>
    run(async () => {
      const value = Number(rate);
      if (!Number.isFinite(value) || value <= 0) throw new ApiError("Enter an hourly rate above zero.");
      if (contractId !== null) setContract(await updateHourlyRate(contractId, value));
      setNotice("Hourly rate saved. It applies to new change orders.");
    });

  const money = new Intl.NumberFormat(undefined, { style: "currency", currency: contract?.currency || "USD" });

  if (contracts !== null && contracts.length === 0 && contractId === null) {
    return (
      <main className="mx-auto max-w-5xl px-4 py-8">
        <h1 className="mb-2 text-2xl font-bold">Messages and approvals</h1>
        {error && <p role="alert" className="mb-3 rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-900">{error}</p>}
        <p className="rounded-lg border border-dashed border-slate-300 p-6 text-sm text-slate-600">
          No approved projects yet. Create one on the New project page, approve it, and it will show up here.
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-5xl space-y-6 px-4 py-8">
      <header className="space-y-2">
        <h1 className="text-2xl font-bold">Messages and approvals</h1>
        <p className="text-sm text-slate-600">
          Paste what your client writes. The AI proposes actions; nothing is invoiced until you approve it.
          {USE_FIXTURES && <span className="ml-2 rounded bg-amber-100 px-2 py-0.5 text-amber-900">Fixture mode: no backend needed</span>}
        </p>
        {contracts && contracts.length > 1 && (
          <select value={contractId ?? ""} onChange={(e) => setContractId(Number(e.target.value))}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm">
            {contracts.map((c) => (
              <option key={c.id} value={c.id}>{c.client_name} (#{c.id})</option>
            ))}
          </select>
        )}
      </header>

      {error && <p role="alert" className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-900">{error}</p>}
      {notice && <p role="status" className="rounded-lg border border-emerald-300 bg-emerald-50 p-3 text-sm text-emerald-900">{notice}</p>}

      {!contract ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : (
        <>
          <section className="space-y-3 rounded-xl border border-slate-200 bg-white p-5">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <h2 className="text-lg font-semibold">{contract.client_name}</h2>
              <label className="flex items-center gap-2 text-sm">
                <span className="font-medium">Hourly rate</span>
                <input value={rate} onChange={(e) => setRate(e.target.value)} inputMode="decimal"
                  className="w-24 rounded-lg border border-slate-300 px-3 py-1.5" />
                <button onClick={saveRate} disabled={busy} className="rounded-lg border border-slate-300 px-3 py-1.5 disabled:opacity-50">
                  Save
                </button>
              </label>
            </div>
            <ul className="divide-y divide-slate-100 text-sm">
              {contract.milestones.map((m) => (
                <li key={m.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                  <span className="font-medium">{m.title}</span>
                  <span className="flex items-center gap-3 text-slate-600">
                    {!m.is_deposit && m.trigger !== "change_order" && m.revision_limit !== null && (
                      <span className="text-xs">revisions {m.revisions_used}/{m.revision_limit}</span>
                    )}
                    <span>{money.format(Number(m.amount ?? 0))}</span>
                    <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs">{m.status}</span>
                  </span>
                </li>
              ))}
            </ul>
          </section>

          <section className="space-y-3 rounded-xl border border-slate-200 bg-white p-5">
            <h2 className="text-lg font-semibold">Add a client message</h2>
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} maxLength={5000}
              placeholder="Paste the client's message here"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            <div className="flex flex-wrap gap-3">
              <button onClick={addMessage} disabled={busy || !text.trim()}
                className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
                {busy ? "Working…" : "Analyse message"}
              </button>
              <button type="button" onClick={() => setText(DEMO_MESSAGE)} disabled={busy}
                className="rounded-lg border border-slate-300 px-4 py-2 text-sm">
                Use demo message
              </button>
            </div>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-semibold">
              Approval inbox <span className="text-sm font-normal text-slate-500">({suggestions.length} waiting)</span>
            </h2>
            {suggestions.length === 0 ? (
              <p className="rounded-lg border border-dashed border-slate-300 p-4 text-sm text-slate-500">
                Nothing is waiting for you. Suggestions from client messages appear here.
              </p>
            ) : (
              <ul className="space-y-3">
                {suggestions.map((s) => (
                  <SuggestionCard key={s.id} suggestion={s} contract={contract} busy={busy} onApprove={approve} onDismiss={dismiss} />
                ))}
              </ul>
            )}
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-semibold">Message thread</h2>
            <MessageThread messages={messages} />
          </section>
        </>
      )}
    </main>
  );
}
