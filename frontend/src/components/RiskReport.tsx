import type { Contract, Risk } from "../types";

const SEVERITY: Record<Risk["severity"], string> = {
  high: "bg-red-100 text-red-800 border-red-300",
  medium: "bg-amber-100 text-amber-800 border-amber-300",
  low: "bg-slate-100 text-slate-700 border-slate-300",
};

const LABEL: Record<string, string> = {
  vague_acceptance: "Payment depends on satisfaction",
  unlimited_revisions: "Unlimited revisions",
  ip_before_payment: "Rights before payment",
  long_payment_terms: "Long payment terms",
  no_kill_fee: "No kill fee",
  no_late_fee: "No late fee",
  undefined_scope: "Undefined scope",
  other: "Other risk",
};

function escapeRegex(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Find each quoted clause in the pasted text, ignoring case and line breaks, and mark it. */
export function ContractText({ text, risks }: { text: string; risks: Risk[] }) {
  const ranges: [number, number][] = [];
  for (const risk of risks) {
    const quote = risk.clause_quote.trim().replace(/[\s.,;:]+$/, "");
    if (!quote) continue;
    const pattern = quote.split(/\s+/).map(escapeRegex).join("\\s+");
    const match = new RegExp(pattern, "i").exec(text);
    if (match) ranges.push([match.index, match.index + match[0].length]);
  }
  ranges.sort((a, b) => a[0] - b[0]);
  const parts: JSX.Element[] = [];
  let cursor = 0;
  for (const [start, end] of ranges) {
    if (start < cursor) continue;
    if (start > cursor) parts.push(<span key={`t${cursor}`}>{text.slice(cursor, start)}</span>);
    parts.push(
      <mark key={`m${start}`} className="rounded bg-red-200 px-0.5 text-red-950">
        {text.slice(start, end)}
      </mark>,
    );
    cursor = end;
  }
  parts.push(<span key="end">{text.slice(cursor)}</span>);
  return (
    <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-lg border border-slate-200 bg-white p-3 font-sans text-sm leading-relaxed">
      {parts}
    </pre>
  );
}

export default function RiskReport({ contract, sourceText }: { contract: Contract; sourceText: string | null }) {
  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">
        Risk report <span className="text-sm font-normal text-slate-500">({contract.risks.length} found)</span>
      </h2>

      {contract.warnings.length > 0 && (
        <ul className="space-y-1 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          {contract.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}

      {sourceText && contract.risks.length > 0 && <ContractText text={sourceText} risks={contract.risks} />}

      {contract.risks.length === 0 ? (
        <p className="rounded-lg border border-emerald-300 bg-emerald-50 p-3 text-sm text-emerald-900">
          No risky clauses were found in this contract.
        </p>
      ) : (
        <ul className="space-y-3">
          {contract.risks.map((risk) => (
            <li key={risk.clause_quote} className="rounded-lg border border-slate-200 bg-white p-4">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${SEVERITY[risk.severity]}`}>
                  {risk.severity}
                </span>
                <span className="text-sm font-semibold">{LABEL[risk.category] ?? risk.category}</span>
              </div>
              <blockquote className="mb-2 border-l-4 border-red-300 pl-3 text-sm italic text-slate-700">
                “{risk.clause_quote}”
              </blockquote>
              <p className="text-sm text-slate-700">{risk.why_it_matters}</p>
              <p className="mt-2 rounded bg-emerald-50 p-2 text-sm text-emerald-900">
                <span className="font-medium">Fairer wording: </span>
                {risk.suggested_rewrite}
              </p>
            </li>
          ))}
        </ul>
      )}

      {contract.ambiguities.length > 0 && (
        <div className="rounded-lg border border-slate-200 bg-white p-3 text-sm">
          <p className="mb-1 font-medium">Worth clarifying with the client</p>
          <ul className="list-disc space-y-1 pl-5 text-slate-700">
            {contract.ambiguities.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
