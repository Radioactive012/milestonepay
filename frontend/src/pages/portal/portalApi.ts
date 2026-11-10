// Calls for the client portal and the freelancer's billing and files panel (Person A's routes).
// Mirrors portal_view() in backend/app/api/portal.py. Money arrives as strings.

export interface PortalFile {
  id: number;
  filename: string;
  content_type: string;
  size_bytes: number;
  has_preview: boolean;
  locked: boolean;
}

export interface PortalInvoice {
  number: string;
  amount: string;
  status: string;
  payer_url: string | null;
  due_date: string | null;
}

export interface PortalMilestone {
  id: number;
  title: string;
  amount: string;
  status: string;
  due_date: string | null;
  trigger_description: string;
  is_deposit: boolean;
  can_approve: boolean;
  approved_by_client: boolean;
  invoice: PortalInvoice | null;
  files: PortalFile[];
}

export interface PortalView {
  client_name: string;
  currency: string;
  status: string;
  total: string;
  paid: string;
  outstanding: string;
  messages?: { body: string; created_at: string }[];
  milestones: PortalMilestone[];
}

/** A message the client wrote on their page, as the freelancer sees it. */
export interface ClientNote {
  id: number;
  body: string;
  status: "waiting" | "analysed" | "dismissed";
  message_id: number | null;
  created_at: string;
}

export interface DemoClock {
  offset_days: number;
  today: string;
  ai_calls_today: number;
  ai_daily_limit: number;
}

export interface JobsSummary {
  today: string;
  paid: string[];
  invoiced: string[];
  overdue: string[];
  reminders: { number: string; stage: number; subject: string }[];
  errors: string[];
}

export class PortalError extends Error {
  constructor(message: string, readonly status = 0) {
    super(message);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new PortalError("Couldn't reach the server. Check your internet connection and try again.");
  }
  if (!response.ok) {
    let detail = `Something went wrong (${response.status}). Please try again.`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* keep the generic message */
    }
    throw new PortalError(detail, response.status);
  }
  return response.json() as Promise<T>;
}

const post = (body?: unknown): RequestInit =>
  body === undefined
    ? { method: "POST" }
    : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };

const t = encodeURIComponent;

// --- client side: everything goes through the contract's private link ---
export const readPortal = (token: string) => call<PortalView>(`/api/portal/${t(token)}`);
export const approveAsClient = (token: string, milestoneId: number) =>
  call<PortalView>(`/api/portal/${t(token)}/milestones/${milestoneId}/approve`, post());
export const writeAsClient = (token: string, body: string) =>
  call<PortalView>(`/api/portal/${t(token)}/messages`, post({ body }));
export const previewUrl = (token: string, fileId: number) => `/api/portal/${t(token)}/files/${fileId}/preview`;
export const downloadUrl = (token: string, fileId: number) => `/api/portal/${t(token)}/files/${fileId}`;

// --- freelancer side ---
export function uploadFile(milestoneId: number, file: File) {
  const form = new FormData();
  form.append("file", file);
  return call<{ id: number; filename: string; has_preview: boolean }>(`/api/milestones/${milestoneId}/files`, {
    method: "POST",
    body: form,
  });
}
export const sendInvoice = (milestoneId: number) => call<unknown>(`/api/milestones/${milestoneId}/invoice`, post());
export const checkPayment = (invoiceId: number) => call<unknown>(`/api/invoices/${invoiceId}/refresh`, post());
export const listClientNotes = (contractId: number) => call<ClientNote[]>(`/api/contracts/${contractId}/client-messages`);
export const analyseClientNote = (noteId: number) =>
  call<{ suggestions: unknown[] }>(`/api/client-messages/${noteId}/analyse`, post());
export const dismissClientNote = (noteId: number) => call<ClientNote>(`/api/client-messages/${noteId}/dismiss`, post());
export const ownFileUrl = (fileId: number) => `/api/files/${fileId}`;
export const portalLink = (token: string) => `${window.location.origin}/portal/${t(token)}`;

// --- demo controls ---
export const readClock = () => call<DemoClock>("/api/demo/clock");
export const setClock = (offsetDays: number) => call<DemoClock>("/api/demo/clock", post({ offset_days: offsetDays }));
export const runJobs = () => call<JobsSummary>("/api/demo/run-jobs", post());
export const loadDemo = () => call<{ id: number }>("/api/demo/load", post());
export const resetDemo = () => call<DemoClock>("/api/demo/reset", post());

export function money(amount: string | number, currency: string) {
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(Number(amount));
  } catch {
    return `${currency} ${amount}`;
  }
}

export function readableSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
