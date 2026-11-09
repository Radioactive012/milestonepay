import { useState } from "react";
import type { Contract, Milestone } from "../../types";
import {
  PortalError, checkPayment, money, ownFileUrl, portalLink, readableSize, sendInvoice, uploadFile,
  type PortalFile,
} from "./portalApi";

type MilestoneWithFiles = Milestone & { files?: PortalFile[] };

const CAN_SEND = new Set(["scheduled", "awaiting_trigger"]);
// deposits and change orders are invoiced straight from draft, so a failed send is retried from here
const RETRY_FROM_DRAFT = new Set(["approval", "change_order"]);
const WAITING = new Set(["invoiced", "overdue"]);

/** The freelancer's side of the client portal: the client's link, files per milestone, and billing buttons. */
export default function BillingPanel({ contract, onChanged }: { contract: Contract; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const link = contract.portal_token ? portalLink(contract.portal_token) : null;

  async function run(work: () => Promise<string>) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      setNotice(await work());
    } catch (e) {
      setError(e instanceof PortalError ? e.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
      onChanged();
    }
  }

  async function copyLink() {
    if (!link) return;
    try {
      await navigator.clipboard.writeText(link);
      setNotice("Link copied. Send it to your client.");
    } catch {
      setNotice("Couldn't copy automatically. Select the link and copy it.");
    }
  }

  const milestones = (contract.milestones as MilestoneWithFiles[]).filter((m) => m.status !== "cancelled");

  return (
    <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-5">
      <div>
        <h2 className="text-lg font-semibold">Billing, files and client page</h2>
        <p className="text-sm text-slate-600">
          Your client sees milestones, invoices with a PayPal button, and watermarked previews. Full files unlock
          by themselves once PayPal says that milestone is paid.
        </p>
      </div>

      {link && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg bg-slate-50 p-3 text-sm">
          <span className="font-medium">Client page:</span>
          <code className="min-w-0 flex-1 select-all truncate rounded bg-white px-2 py-1 text-xs" title={link}>{link}</code>
          <button onClick={copyLink} className="rounded-lg border border-slate-300 bg-white px-3 py-1.5">Copy</button>
          <a href={link} target="_blank" rel="noopener noreferrer" className="rounded-lg border border-slate-300 bg-white px-3 py-1.5">
            Open as client
          </a>
        </div>
      )}

      {error && <p role="alert" className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-900">{error}</p>}
      {notice && <p role="status" className="rounded-lg border border-emerald-300 bg-emerald-50 p-3 text-sm text-emerald-900">{notice}</p>}

      <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
        {milestones.map((m) => (
          <li key={m.id} className="space-y-2 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-medium">
                {m.title} <span className="font-normal text-slate-500">· {money(m.amount ?? "0", contract.currency)}</span>
              </span>
              <div className="flex flex-wrap gap-2">
                {(CAN_SEND.has(m.status) || (m.status === "draft" && contract.status === "active" && RETRY_FROM_DRAFT.has(m.trigger))) && (
                  <button
                    disabled={busy}
                    onClick={() => run(async () => {
                      await sendInvoice(m.id);
                      return `Invoice for "${m.title}" sent through PayPal.`;
                    })}
                    className="rounded-lg bg-slate-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
                  >
                    Send invoice now
                  </button>
                )}
                {WAITING.has(m.status) && m.invoice && (
                  <button
                    disabled={busy}
                    onClick={() => run(async () => {
                      await checkPayment(m.invoice!.id);
                      return "Checked with PayPal. The status below is up to date.";
                    })}
                    className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-50"
                  >
                    Check payment
                  </button>
                )}
                <label className={`cursor-pointer rounded-lg border border-slate-300 px-3 py-1.5 text-sm ${busy ? "opacity-50" : ""}`}>
                  Add file
                  <input
                    type="file"
                    className="sr-only"
                    disabled={busy}
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      e.target.value = "";
                      if (file) run(async () => {
                        const saved = await uploadFile(m.id, file);
                        return saved.has_preview
                          ? `"${saved.filename}" added. Your client sees a watermarked preview until it's paid.`
                          : `"${saved.filename}" added. Your client can download it once it's paid.`;
                      });
                    }}
                  />
                </label>
              </div>
            </div>
            {(m.files ?? []).length > 0 && (
              <ul className="flex flex-wrap gap-2 text-xs">
                {m.files!.map((f) => (
                  <li key={f.id}>
                    <a href={ownFileUrl(f.id)} className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-3 py-1 hover:bg-slate-200">
                      {f.locked ? "🔒" : "✅"} {f.filename} ({readableSize(f.size_bytes)})
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
