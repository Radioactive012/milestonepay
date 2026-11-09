import { useEffect, useState } from "react";
import { ApiError, USE_FIXTURES, approveContract, createContract, readContract, refreshInvoice, updateMilestone } from "../api";
import MilestoneGrid from "../components/MilestoneGrid";
import RiskReport from "../components/RiskReport";
import { DEMO_CONTRACT_TEXT } from "../fixtures";
import type { Contract, MilestoneChanges } from "../types";

type Step = "input" | "analysing" | "review" | "approving" | "approved";
const DEPOSITS = [0, 25, 30, 50];

interface Props {
  /** Open this saved draft for review instead of starting empty (used by the demo bar). */
  draftId?: number | null;
  onApproved?: (contractId: number) => void;
  onOpenProject?: () => void;
}

export default function NewProject({ draftId, onApproved, onOpenProject }: Props) {
  const [step, setStep] = useState<Step>("input");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [rate, setRate] = useState("40");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [contract, setContract] = useState<Contract | null>(null);
  const [deposit, setDeposit] = useState(25);
  const [error, setError] = useState<string | null>(null);
  const [gridKey, setGridKey] = useState(0);

  const fail = (e: unknown) => setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");

  useEffect(() => {
    if (!draftId) return;
    readContract(draftId)
      .then((draft) => {
        if (draft.status !== "draft") return;
        setContract(draft);
        setEmail(draft.client_email);
        setName(draft.client_name);
        setRate(Number(draft.hourly_rate).toFixed(2));
        setDeposit(draft.deposit_pct_suggested);
        setStep("review");
      })
      .catch(fail);
  }, [draftId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function analyse() {
    setError(null);
    if (!email.includes("@")) return setError("Enter the client's email address.");
    if (!text.trim() && !file) return setError("Paste the contract text or choose a file.");
    const hourlyRate = Number(rate);
    if (!Number.isFinite(hourlyRate) || hourlyRate <= 0) return setError("Enter an hourly rate above zero.");
    setStep("analysing");
    try {
      const result = await createContract({ clientEmail: email, clientName: name || undefined, hourlyRate, text: text.trim() || undefined, file });
      setContract(result);
      setDeposit(result.deposit_pct_suggested);
      setStep("review");
    } catch (e) {
      fail(e);
      setStep("input");
    }
  }

  async function saveEdit(id: number, changes: MilestoneChanges) {
    setError(null);
    try {
      setContract(await updateMilestone(id, changes));
      return true;
    } catch (e) {
      fail(e);
      setGridKey((k) => k + 1); // reset the grid to the last saved values
      return false;
    }
  }

  async function approve() {
    if (!contract) return;
    setError(null);
    setStep("approving");
    try {
      const approved = await approveContract(contract.id, deposit);
      setContract(approved);
      onApproved?.(approved.id);
      setStep("approved");
    } catch (e) {
      fail(e);
      setStep("review");
    }
  }

  async function refresh(invoiceId: number) {
    setError(null);
    try {
      setContract(await refreshInvoice(invoiceId));
    } catch (e) {
      fail(e);
    }
  }

  const depositMilestone = contract?.milestones.find((m) => m.is_deposit);
  const busy = step === "analysing" || step === "approving";

  return (
    <main className="mx-auto max-w-5xl space-y-6 px-4 py-8">
      <header>
        <h1 className="text-2xl font-bold">New project</h1>
        <p className="text-sm text-slate-600">
          Paste a contract. The AI finds the milestones and risky clauses; you check them, then approve.
          {USE_FIXTURES && <span className="ml-2 rounded bg-amber-100 px-2 py-0.5 text-amber-900">Fixture mode: no backend needed</span>}
        </p>
      </header>

      {error && (
        <p role="alert" className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-900">
          {error}
        </p>
      )}

      {(step === "input" || step === "analysing") && (
        <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="text-sm">
              <span className="mb-1 block font-medium">Client email</span>
              <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" placeholder="client@example.com"
                className="w-full rounded-lg border border-slate-300 px-3 py-2" />
            </label>
            <label className="text-sm">
              <span className="mb-1 block font-medium">Client name <span className="font-normal text-slate-500">(optional)</span></span>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Read from the contract if blank"
                className="w-full rounded-lg border border-slate-300 px-3 py-2" />
            </label>
          </div>
          <label className="block text-sm sm:max-w-xs">
            <span className="mb-1 block font-medium">Hourly rate <span className="font-normal text-slate-500">(prices extra work)</span></span>
            <input value={rate} onChange={(e) => setRate(e.target.value)} inputMode="decimal"
              className="w-full rounded-lg border border-slate-300 px-3 py-2" />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium">Contract text</span>
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={10} placeholder="Paste the contract here"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 font-sans" />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium">Or upload a PDF or photo <span className="font-normal text-slate-500">(max 10 MB)</span></span>
            <input type="file" accept="application/pdf,image/png,image/jpeg,image/webp"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </label>
          <div className="flex flex-wrap gap-3">
            <button onClick={analyse} disabled={busy}
              className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
              {step === "analysing" ? "Reading the contract…" : "Analyse contract"}
            </button>
            <button type="button" disabled={busy}
              onClick={() => { setText(DEMO_CONTRACT_TEXT); setEmail("owner@harborlane.example"); setName("Harbor Lane Bakery"); }}
              className="rounded-lg border border-slate-300 px-4 py-2 text-sm">
              Load demo contract
            </button>
          </div>
        </section>
      )}

      {contract && (step === "review" || step === "approving" || step === "approved") && (
        <>
          <p className="text-sm text-slate-600">
            {contract.client_name} · {contract.client_email} · {contract.currency} · pays within {contract.payment_terms_days} days
          </p>

          <RiskReport contract={contract} sourceText={text.trim() || null} />

          <section className="space-y-3">
            <h2 className="text-lg font-semibold">Milestones</h2>
            {step !== "approved" && <p className="text-sm text-slate-600">Click a cell to edit it. Changes save as you go.</p>}
            <MilestoneGrid contract={contract} onEdit={saveEdit} gridKey={gridKey} />
            {contract.stated_total && contract.milestone_total !== contract.stated_total && (
              <p className="text-sm text-amber-800">
                The milestones add up to {contract.milestone_total}, but the contract total is {contract.stated_total}.
              </p>
            )}
          </section>

          {step !== "approved" ? (
            <section className="space-y-3 rounded-xl border border-slate-200 bg-white p-5">
              <h2 className="text-lg font-semibold">Approve and ask for a deposit</h2>
              <p className="text-sm text-slate-600">{contract.deposit_rationale}</p>
              <label className="flex items-center gap-3 text-sm">
                <span className="font-medium">Deposit</span>
                <select value={deposit} onChange={(e) => setDeposit(Number(e.target.value))}
                  className="rounded-lg border border-slate-300 px-3 py-2">
                  {DEPOSITS.map((d) => (
                    <option key={d} value={d}>{d}%{d === contract.deposit_pct_suggested ? " (suggested)" : ""}</option>
                  ))}
                </select>
              </label>
              <button onClick={approve} disabled={busy}
                className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
                {step === "approving" ? "Sending the deposit invoice…" : "Approve and send deposit invoice"}
              </button>
            </section>
          ) : (
            <section className="space-y-3 rounded-xl border border-emerald-300 bg-emerald-50 p-5">
              <h2 className="text-lg font-semibold text-emerald-900">Approved</h2>
              {depositMilestone?.invoice ? (
                <>
                  <p className="text-sm text-emerald-900">
                    Deposit invoice {depositMilestone.invoice.number} for {depositMilestone.invoice.amount} {contract.currency} is{" "}
                    <strong>{depositMilestone.invoice.status}</strong>.
                  </p>
                  <div className="flex flex-wrap gap-3">
                    {depositMilestone.invoice.payer_url && (
                      <a href={depositMilestone.invoice.payer_url} target="_blank" rel="noreferrer"
                        className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white">
                        Open the payer link
                      </a>
                    )}
                    <button onClick={() => refresh(depositMilestone.invoice!.id)}
                      className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm">
                      Refresh from PayPal
                    </button>
                  </div>
                </>
              ) : (
                <p className="text-sm text-emerald-900">
                  The milestones are approved{deposit === 0 ? " with no deposit." : "."}
                </p>
              )}
              {onOpenProject && (
                <button onClick={onOpenProject} className="rounded-lg border border-emerald-700 bg-white px-4 py-2 text-sm font-medium text-emerald-900">
                  Go to messages and approvals
                </button>
              )}
            </section>
          )}
        </>
      )}
    </main>
  );
}
