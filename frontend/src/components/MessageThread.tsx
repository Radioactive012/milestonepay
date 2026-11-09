import type { ThreadMessage } from "../types";

const TAG: Record<string, string> = {
  milestone_reached: "Milestone reached",
  scope_creep: "Extra work",
  extra_revision: "Revision",
};

const STATUS_STYLE: Record<string, string> = {
  pending: "border-sky-300 bg-sky-50 text-sky-900",
  approved: "border-emerald-300 bg-emerald-50 text-emerald-900",
  dismissed: "border-slate-300 bg-slate-100 text-slate-600 line-through",
};

export default function MessageThread({ messages }: { messages: ThreadMessage[] }) {
  if (messages.length === 0) {
    return <p className="rounded-lg border border-dashed border-slate-300 p-4 text-sm text-slate-500">No messages yet. Paste one above.</p>;
  }
  return (
    <ul className="space-y-3">
      {messages.map((m) => (
        <li key={m.id} className="rounded-xl border border-slate-200 bg-white p-4">
          <p className="whitespace-pre-wrap text-sm">{m.body}</p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="text-xs text-slate-500">
              {m.sender === "client" ? "Client" : m.sender === "freelancer" ? "You" : "Pasted"} ·{" "}
              {new Date(m.created_at).toLocaleString()}
            </span>
            {m.tags.map((t, i) => (
              <span key={i} className={`rounded-full border px-2 py-0.5 text-xs ${STATUS_STYLE[t.status] ?? ""}`}>
                {TAG[t.type] ?? t.type} · {t.status}
              </span>
            ))}
            {m.tags.length === 0 && <span className="text-xs text-slate-400">Nothing for you to act on</span>}
          </div>
          {m.analysis.dropped && m.analysis.dropped.length > 0 && (
            <ul className="mt-2 space-y-1 text-xs text-slate-500">
              {m.analysis.dropped.map((d) => (
                <li key={d}>AI note: {d}</li>
              ))}
            </ul>
          )}
        </li>
      ))}
    </ul>
  );
}
