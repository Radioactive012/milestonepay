// Mirrors contract_out() in backend/app/api/contracts.py. Money arrives as strings.
export type RiskCategory =
  | "vague_acceptance" | "unlimited_revisions" | "ip_before_payment" | "long_payment_terms"
  | "no_kill_fee" | "no_late_fee" | "undefined_scope" | "other";

export interface Risk {
  clause_quote: string;
  category: RiskCategory;
  severity: "low" | "medium" | "high";
  why_it_matters: string;
  suggested_rewrite: string;
}

export interface Invoice {
  id: number;
  number: string | null;
  paypal_invoice_id: string | null;
  amount: string | null;
  status: string;
  payer_url: string | null;
  due_date: string | null;
  paid_at: string | null;
}

export interface Milestone {
  id: number;
  position: number;
  title: string;
  amount: string | null;
  trigger: string;
  trigger_description: string | null;
  due_date: string | null;
  revision_limit: number | null;
  revisions_used: number;
  is_deposit: boolean;
  status: string;
  invoice: Invoice | null;
}

export interface AuditItem {
  actor: string;
  action: string;
  details: Record<string, unknown>;
  at: string;
}

export interface ChangeOrder {
  id: number;
  description: string;
  estimated_hours: string;
  price: string;
  milestone_id: number;
  suggestion_id: number | null;
}

export interface Contract {
  id: number;
  client_name: string;
  client_email: string;
  currency: string;
  stated_total: string | null;
  milestone_total: string | null;
  payment_terms_days: number;
  hourly_rate: string;
  status: string;
  portal_token: string | null;
  risks: Risk[];
  warnings: string[];
  ambiguities: string[];
  deposit_pct_suggested: number;
  deposit_rationale: string;
  milestones: Milestone[];
  change_orders: ChangeOrder[];
  audit: AuditItem[];
}

export type MilestoneChanges = Partial<{
  title: string;
  amount: number;
  trigger: "date" | "event";
  due_date: string | null;
  trigger_description: string;
}>;

export interface ContractSummary {
  id: number;
  client_name: string;
  currency: string;
  status: string;
  created_at: string;
}

export type SuggestionType = "milestone_reached" | "scope_creep" | "extra_revision";

export interface Suggestion {
  id: number;
  contract_id: number;
  message_id: number | null;
  milestone_id: number | null;
  type: SuggestionType;
  payload: Record<string, string | number | boolean | null>;
  evidence_quote: string;
  confidence: number;
  /** Below the confidence bar: shown as "Possible", with no approve button. */
  possible: boolean;
  status: "pending" | "approved" | "dismissed";
  message_body: string | null;
  created_at: string;
}

export interface MessageTag {
  type: string;
  status: string;
}

export interface ThreadMessage {
  id: number;
  contract_id: number;
  sender: "client" | "freelancer" | "pasted";
  body: string;
  analysis: { dropped?: string[] };
  tags: MessageTag[];
  created_at: string;
}

export interface PostMessageResult {
  message: ThreadMessage;
  suggestions: Suggestion[];
  dropped: string[];
}

export interface ApproveResult {
  suggestion: Suggestion;
  contract: Contract;
}

export interface ApproveEdits {
  hours?: number;
  description?: string;
}
