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

export interface Contract {
  id: number;
  client_name: string;
  client_email: string;
  currency: string;
  stated_total: string | null;
  milestone_total: string | null;
  payment_terms_days: number;
  status: string;
  portal_token: string | null;
  risks: Risk[];
  warnings: string[];
  ambiguities: string[];
  deposit_pct_suggested: number;
  deposit_rationale: string;
  milestones: Milestone[];
  audit: AuditItem[];
}

export type MilestoneChanges = Partial<{
  title: string;
  amount: number;
  trigger: "date" | "event";
  due_date: string | null;
  trigger_description: string;
}>;
