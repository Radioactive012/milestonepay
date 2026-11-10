import { useCallback, useEffect, useRef, useState } from "react";
import {
  PortalError, approveAsClient, downloadUrl, money, previewUrl, readPortal, readableSize, writeAsClient,
  type PortalMilestone, type PortalView,
} from "./portalApi";

// What the client sees for each milestone status
const STATUS: Record<string, { label: string; style: string }> = {
  draft: { label: "Being prepared", style: "bg-slate-100 text-slate-700" },
  scheduled: { label: "Scheduled", style: "bg-slate-100 text-slate-700" },
  awaiting_trigger: { label: "In progress", style: "bg-sky-100 text-sky-900" },
  invoiced: { label: "Invoice sent", style: "bg-amber-100 text-amber-900" },
  overdue: { label: "Overdue", style: "bg-red-100 text-red-800" },
  paid: { label: "Paid", style: "bg-emerald-100 text-emerald-800" },
};

const WAITING_FOR_PAYMENT = new Set(["invoiced", "overdue"]);

function formatDate(value: string | null) {
  if (!value) return null;
  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export default function PortalPage({ token }: { token: string }) {
  const [view, setView] = useState<PortalView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [confirming, setConfirming] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const messageRef = useRef<HTMLDivElement>(null);

  // the buttons are further down the page, so bring a new message into view
  useEffect(() => {
    if (error || notice) messageRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [error, notice]);

  const load = useCallback(async () => {
    try {
      // doesn't clear an error on purpose: a refresh right after a failed action must keep its message
      setView(await readPortal(token));
    } catch (e) {
      if (e instanceof PortalError && e.status === 404) setNotFound(true);
      else setError(e instanceof PortalError ? e.message : "Something went wrong. Please try again.");
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  // While an invoice is open, check every 10 seconds so a payment shows up without a reload
  const waiting = view?.milestones.some((m) => WAITING_FOR_PAYMENT.has(m.status)) ?? false;
  useEffect(() => {
    if (!waiting) return;
    const timer = window.setInterval(load, 10_000);
    return () => window.clearInterval(timer);
  }, [waiting, load]);

  async function approve(milestone: PortalMilestone) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const next = await approveAsClient(token, milestone.id);
      setView(next);
      const after = next.milestones.find((m) => m.id === milestone.id);
      setNotice(
        after?.invoice
          ? `Thanks! You approved "${milestone.title}". The invoice is ready below.`
          : `Thanks! You approved "${milestone.title}". The invoice will come on its due date.`,
      );
    } catch (e) {
      setError(e instanceof PortalError ? e.message : "Something went wrong. Please try again.");
      load();
    } finally {
      setBusy(false);
      setConfirming(null);
    }
  }

  if (notFound) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-16 text-center">
        <h1 className="mb-2 text-2xl font-bold">This link doesn't work</h1>
        <p className="text-slate-600">It may be mistyped or out of date. Ask your freelancer to send you the link again.</p>
      </main>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-4 py-3">
          <span className="text-lg font-bold">MilestonePay</span>
          <span className="text-sm text-slate-500">Client page</span>
        </div>
      </header>

      <main className="mx-auto max-w-3xl space-y-6 px-4 py-8">
        {!view && !error && <p className="text-sm text-slate-500">Loading your project…</p>}
        <div ref={messageRef} className="space-y-3 empty:hidden">
          {error && <p role="alert" className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-900">{error}</p>}
          {notice && <p role="status" className="rounded-lg border border-emerald-300 bg-emerald-50 p-3 text-sm text-emerald-900">{notice}</p>}
        </div>

        {view && (
          <>
            <section>
              <h1 className="text-2xl font-bold">{view.client_name}</h1>
              <p className="text-sm text-slate-600">Your project's payments, invoices and files in one place.</p>
            </section>

            {view.status === "draft" ? (
              <p className="rounded-xl border border-dashed border-slate-300 bg-white p-6 text-sm text-slate-600">
                Your freelancer is still setting up this project. Check back soon.
              </p>
            ) : (
              <>
                <section className="grid gap-4 sm:grid-cols-3">
                  {[
                    { label: "Project total", value: view.total, style: "border-slate-200" },
                    { label: "Paid", value: view.paid, style: "border-emerald-300 bg-emerald-50" },
                    { label: "Still to pay", value: view.outstanding, style: "border-slate-200" },
                  ].map((tile) => (
                    <div key={tile.label} className={`rounded-xl border bg-white p-4 ${tile.style}`}>
                      <p className="text-sm text-slate-600">{tile.label}</p>
                      <p className="text-2xl font-bold">{money(tile.value, view.currency)}</p>
                    </div>
                  ))}
                </section>

                <section className="space-y-4">
                  <div className="flex items-center justify-between">
                    <h2 className="text-lg font-semibold">Milestones</h2>
                    <button
                      onClick={() => {
                        setError(null);
                        setNotice(null);
                        load();
                      }}
                      className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm"
                    >
                      Refresh
                    </button>
                  </div>
                  <ul className="space-y-4">
                    {view.milestones.map((m) => (
                      <MilestoneCard
                        key={m.id}
                        milestone={m}
                        currency={view.currency}
                        token={token}
                        busy={busy}
                        confirming={confirming === m.id}
                        onAsk={() => setConfirming(m.id)}
                        onCancel={() => setConfirming(null)}
                        onApprove={() => approve(m)}
                      />
                    ))}
                  </ul>
                </section>

                <MessageBox token={token} sent={view.messages ?? []} onSent={setView} />
              </>
            )}

            <p className="text-center text-xs text-slate-500">
              Payments go through PayPal. This demo uses PayPal's sandbox, so no real money moves.
            </p>
          </>
        )}
      </main>
    </div>
  );
}

/** The client writes to the freelancer. It's only saved; the freelancer decides what to do with it. */
function MessageBox({ token, sent, onSent }: {
  token: string;
  sent: { body: string; created_at: string }[];
  onSent: (view: PortalView) => void;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function send() {
    setBusy(true);
    setError(null);
    setDone(false);
    try {
      onSent(await writeAsClient(token, text.trim()));
      setText("");
      setDone(true);
    } catch (e) {
      setError(e instanceof PortalError ? e.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-3 rounded-xl border border-slate-200 bg-white p-5">
      <div>
        <h2 className="text-lg font-semibold">Message your freelancer</h2>
        <p className="text-sm text-slate-600">Feedback, approvals or new requests. Your freelancer reads every message.</p>
      </div>
      <textarea
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setDone(false);
        }}
        maxLength={2000}
        rows={4}
        placeholder="For example: The sketches look great! Could you also design a matching menu?"
        aria-label="Your message"
        className="w-full rounded-lg border border-slate-300 p-3 text-sm"
      />
      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={send}
          disabled={busy || !text.trim()}
          className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {busy ? "Sending…" : "Send message"}
        </button>
        {done && <span role="status" className="text-sm text-emerald-700">Sent. Your freelancer will get back to you.</span>}
      </div>
      {error && <p role="alert" className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-900">{error}</p>}
      {sent.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium">Your messages</h3>
          <ul className="space-y-2">
            {sent.map((m, i) => (
              <li key={i} className="rounded-lg bg-slate-50 p-3 text-sm">
                <p className="whitespace-pre-wrap">{m.body}</p>
                <p className="mt-1 text-xs text-slate-500">{new Date(m.created_at).toLocaleString()}</p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

interface CardProps {
  milestone: PortalMilestone;
  currency: string;
  token: string;
  busy: boolean;
  confirming: boolean;
  onAsk: () => void;
  onCancel: () => void;
  onApprove: () => void;
}

function MilestoneCard({ milestone: m, currency, token, busy, confirming, onAsk, onCancel, onApprove }: CardProps) {
  const status = STATUS[m.status] ?? { label: m.status, style: "bg-slate-100 text-slate-700" };
  const invoice = m.invoice;
  const canPay = invoice && invoice.status === "SENT" && invoice.payer_url && m.status !== "paid";
  const due = formatDate(invoice?.due_date ?? m.due_date);

  return (
    <li className="space-y-3 rounded-xl border border-slate-200 bg-white p-5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="font-semibold">{m.title}</h3>
          {m.trigger_description && <p className="text-sm text-slate-600">{m.trigger_description}</p>}
        </div>
        <div className="text-right">
          <p className="text-lg font-bold">{money(m.amount, currency)}</p>
          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${status.style}`}>{status.label}</span>
        </div>
      </div>

      {invoice && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-slate-50 p-3 text-sm">
          <span className="text-slate-700">
            Invoice {invoice.number}
            {due && m.status !== "paid" && <> · due {due}</>}
          </span>
          {canPay ? (
            <a
              href={invoice.payer_url!}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-lg bg-[#0070ba] px-4 py-2 font-medium text-white hover:bg-[#005ea6]"
            >
              Pay {money(invoice.amount, currency)} with PayPal
            </a>
          ) : (
            m.status === "paid" && <span className="font-medium text-emerald-700">Paid. Thank you!</span>
          )}
        </div>
      )}
      {canPay && (
        <p className="text-xs text-slate-500">After you pay, this page updates by itself within a few seconds.</p>
      )}

      {m.approved_by_client && !m.can_approve && !m.invoice && (
        <p className="text-sm font-medium text-emerald-700">You approved this work. The invoice will come on its due date.</p>
      )}

      {m.can_approve &&
        (confirming ? (
          <div className="space-y-2 rounded-lg border border-sky-200 bg-sky-50 p-3 text-sm">
            <p>
              Approving tells your freelancer this work is accepted.
              {m.status === "awaiting_trigger"
                ? ` An invoice for ${money(m.amount, currency)} will be sent to you right away.`
                : " The invoice will come on its due date."}
            </p>
            <div className="flex gap-2">
              <button onClick={onApprove} disabled={busy}
                className="rounded-lg bg-slate-900 px-4 py-2 font-medium text-white disabled:opacity-50">
                {busy ? "Approving…" : "Yes, approve"}
              </button>
              <button onClick={onCancel} disabled={busy} className="rounded-lg border border-slate-300 bg-white px-4 py-2">
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <button onClick={onAsk} disabled={busy}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium hover:bg-slate-50 disabled:opacity-50">
            Approve this work
          </button>
        ))}

      {m.files.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-sm font-medium">Files</h4>
          <ul className="grid gap-3 sm:grid-cols-2">
            {m.files.map((f) => (
              <li key={f.id} className="overflow-hidden rounded-lg border border-slate-200">
                {f.has_preview && (
                  <img
                    src={previewUrl(token, f.id)}
                    alt={f.locked ? `Watermarked preview of ${f.filename}` : f.filename}
                    className="aspect-video w-full bg-slate-100 object-contain"
                  />
                )}
                <div className="flex items-center justify-between gap-2 p-3 text-sm">
                  <span className="min-w-0 truncate" title={f.filename}>
                    {f.filename} <span className="text-slate-500">({readableSize(f.size_bytes)})</span>
                  </span>
                  {f.locked ? (
                    <span className="shrink-0 text-xs text-slate-500">🔒 Unlocks when paid</span>
                  ) : (
                    <a href={downloadUrl(token, f.id)} download
                      className="shrink-0 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white">
                      Download
                    </a>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </li>
  );
}
