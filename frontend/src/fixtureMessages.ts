import type { Contract, SuggestionType } from "./types";

export interface Draft {
  type: SuggestionType;
  milestoneId: number | null;
  payload: Record<string, string | number | boolean | null>;
  quote: string;
  confidence: number;
}

const sentences = (text: string) => text.split(/(?<=[.!?])\s+/).map((s) => s.trim()).filter(Boolean);

/** A tiny keyword stand-in for the AI, only used in fixture mode so the screens can be shown without the backend. */
export function fakeAnalyse(text: string, contract: Contract): { drafts: Draft[]; dropped: string[] } {
  const dropped: string[] = [];
  if (/ignore (the|all|previous|your)/i.test(text)) {
    return { drafts: [], dropped: ["The message tried to give the AI instructions, so it was ignored."] };
  }
  const drafts: Draft[] = [];
  const milestones = contract.milestones.filter((m) => !m.is_deposit);
  const mentioned = milestones.filter((m) => text.toLowerCase().includes(m.title.toLowerCase()));

  for (const m of mentioned) {
    const sentence = sentences(text).find((s) => s.toLowerCase().includes(m.title.toLowerCase())) ?? text;
    if (/approv|accept|received|love|perfect/i.test(sentence) && !/not approved/i.test(sentence)) {
      if (m.status === "scheduled" || m.status === "awaiting_trigger") {
        drafts.push({ type: "milestone_reached", milestoneId: m.id, payload: { milestone_title: m.title, amount: m.amount }, quote: sentence, confidence: 0.95 });
      } else {
        dropped.push(`'${m.title}' is already ${m.status}, so no invoice was proposed.`);
      }
    }
  }

  const extra = /(could you also|can you also|please also|we also need|also (?:add|design|build))\s+([^.!?]+)/i.exec(text);
  if (extra) {
    const request = extra[0].trim();
    const description = extra[2].replace(/^(add|design|build)\s+/i, "").trim();
    drafts.push({
      type: "scope_creep",
      milestoneId: null,
      payload: {
        description: description.charAt(0).toUpperCase() + description.slice(1),
        request_quote: request,
        contract_clause_quote: "Anything else is outside this contract and is quoted separately.",
        reason: "This work is not part of the contract's scope.",
        estimated_hours: "4.00",
        hourly_rate: contract.hourly_rate,
        price: (4 * Number(contract.hourly_rate)).toFixed(2),
      },
      quote: request,
      confidence: 0.9,
    });
  }

  const wantsChange = /(tweak|change|revise|different colou?rs|another round|not approved)/i.test(text);
  if (wantsChange) {
    const m = mentioned[0] ?? milestones[0];
    if (m) {
      const sentence = sentences(text).find((s) => /(tweak|change|revise|different colou?rs|another round|not approved)/i.test(s)) ?? text;
      drafts.push({
        type: "extra_revision",
        milestoneId: m.id,
        payload: {
          milestone_title: m.title,
          revisions_used: m.revisions_used,
          revision_limit: m.revision_limit,
          over_limit: m.revision_limit !== null && m.revisions_used + 1 > m.revision_limit,
        },
        quote: sentence,
        confidence: 0.8,
      });
    }
  }
  return { drafts, dropped };
}
