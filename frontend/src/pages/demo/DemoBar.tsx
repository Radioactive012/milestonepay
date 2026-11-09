import { useEffect, useState } from "react";
import {
  PortalError, loadDemo, readClock, resetDemo, runJobs, setClock, type DemoClock, type JobsSummary,
} from "../portal/portalApi";

const MESSAGE_KEY = "milestonepay-demo-message";
const DRAFT_KEY = "milestonepay-open-draft";

/** The draft the demo bar just loaded, if any, so the app can open it once after the reload. */
export function takeDraftToOpen(): number | null {
  try {
    const id = sessionStorage.getItem(DRAFT_KEY);
    sessionStorage.removeItem(DRAFT_KEY);
    return id ? Number(id) : null;
  } catch {
    return null;
  }
}

function remember(message: string) {
  try {
    sessionStorage.setItem(MESSAGE_KEY, message);
  } catch {
    /* the message is a nice-to-have */
  }
}

function recall(): string | null {
  try {
    const message = sessionStorage.getItem(MESSAGE_KEY);
    sessionStorage.removeItem(MESSAGE_KEY);
    return message;
  } catch {
    return null;
  }
}

function describe(summary: JobsSummary) {
  const parts = [
    summary.invoiced.length && `${summary.invoiced.length} invoice(s) sent`,
    summary.overdue.length && `${summary.overdue.length} invoice(s) now overdue`,
    summary.reminders.length && `${summary.reminders.length} PayPal reminder(s) sent`,
  ].filter(Boolean);
  const done = parts.length ? parts.join(", ") : "nothing needed doing";
  const errors = summary.errors.length ? ` Problems: ${summary.errors.join("; ")}` : "";
  return `Daily jobs for ${summary.today}: ${done}.${errors}`;
}

/** Demo controls for the video and for judges. Hidden when the backend has DEMO_MODE=false. */
export default function DemoBar() {
  const [clock, setClockState] = useState<DemoClock | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(recall);
  const [confirmReset, setConfirmReset] = useState(false);

  useEffect(() => {
    readClock().then(setClockState).catch(() => setClockState(null));
  }, []);

  if (!clock) return null;

  async function act(work: () => Promise<string>) {
    setBusy(true);
    try {
      remember(await work());
      window.location.reload();
    } catch (e) {
      setMessage(e instanceof PortalError ? e.message : "Something went wrong. Please try again.");
      setBusy(false);
    }
  }

  const button = "rounded-lg border border-amber-300 bg-white px-3 py-1 text-xs font-medium hover:bg-amber-100 disabled:opacity-50";

  return (
    <div className="border-b border-amber-200 bg-amber-50 text-sm text-amber-950">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-2 px-4 py-2">
        <span className="font-semibold">Demo</span>
        <span>
          Today in the app: {clock.today}
          {clock.offset_days > 0 && ` (+${clock.offset_days} days)`}
        </span>
        <span className="text-amber-800">· AI calls today: {clock.ai_calls_today}/{clock.ai_daily_limit}</span>
        <span className="flex flex-wrap gap-2 sm:ml-auto">
          <button className={button} disabled={busy}
            onClick={() => act(async () => {
              const draft = await loadDemo();
              try {
                sessionStorage.setItem(DRAFT_KEY, String(draft.id));
              } catch {
                /* the app just opens on the dashboard instead */
              }
              return "Demo project loaded from a saved AI reading, so no AI credit was used. Review it and approve it below.";
            })}>
            Load demo project
          </button>
          <button className={button} disabled={busy}
            onClick={() => act(async () => {
              const next = await setClock(clock.offset_days + 7);
              return `Moved forward 7 days. The app now thinks it's ${next.today}. Run the daily jobs to see what happens.`;
            })}>
            +7 days
          </button>
          {clock.offset_days > 0 && (
            <button className={button} disabled={busy}
              onClick={() => act(async () => {
                await setClock(0);
                return "Back to today's real date.";
              })}>
              Back to today
            </button>
          )}
          <button className={button} disabled={busy} onClick={() => act(async () => describe(await runJobs()))}>
            Run daily jobs
          </button>
          {confirmReset ? (
            <>
              <button className={`${button} border-red-300 text-red-800`} disabled={busy}
                onClick={() => act(async () => {
                  await resetDemo();
                  return "Demo reset: all projects removed and the clock is back to today.";
                })}>
                Yes, delete everything
              </button>
              <button className={button} disabled={busy} onClick={() => setConfirmReset(false)}>Cancel</button>
            </>
          ) : (
            <button className={button} disabled={busy} onClick={() => setConfirmReset(true)}>Reset demo</button>
          )}
        </span>
      </div>
      {message && (
        <div className="mx-auto flex max-w-5xl items-start justify-between gap-3 px-4 pb-2">
          <p role="status">{message}</p>
          <button onClick={() => setMessage(null)} className="text-xs underline">Close</button>
        </div>
      )}
    </div>
  );
}
