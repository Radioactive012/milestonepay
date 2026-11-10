import type { ColDef } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { useMemo, useState } from "react";
import { isOverdue } from "../lib/totals";
import type { AuditItem, Contract } from "../types";

const defaultColDef: ColDef = { sortable: true, resizable: true, filter: true };

function useMoney(currency: string) {
  return useMemo(() => new Intl.NumberFormat(undefined, { style: "currency", currency: currency || "USD" }), [currency]);
}

const STATUS_COLOURS: Record<string, string> = {
  paid: "text-emerald-700 font-medium",
  PAID: "text-emerald-700 font-medium",
  overdue: "text-red-700 font-medium",
  invoiced: "text-sky-700",
  SENT: "text-sky-700",
};

// ---- milestones ----
export function MilestonesGrid({ contract }: { contract: Contract }) {
  const money = useMoney(contract.currency);
  const columns = useMemo<ColDef<Contract["milestones"][number]>[]>(
    () => [
      {
        headerName: "#", field: "position", width: 80,
        valueFormatter: (p) => (p.data?.is_deposit ? "" : String(p.value ?? "")),
      },
      { headerName: "Milestone", field: "title", flex: 2, minWidth: 180 },
      {
        headerName: "Amount", field: "amount", width: 130, type: "rightAligned",
        valueGetter: (p) => (p.data?.amount == null ? null : Number(p.data.amount)),
        valueFormatter: (p) => (p.value == null ? "" : money.format(p.value)),
        filter: "agNumberColumnFilter",
      },
      {
        headerName: "Paid when", field: "trigger", width: 140,
        valueFormatter: (p) => ({ approval: "on approval", change_order: "change order" } as Record<string, string>)[p.value] ?? p.value,
      },
      {
        headerName: "Revisions", width: 120,
        valueGetter: (p) => {
          if (!p.data || p.data.is_deposit || p.data.trigger === "change_order") return "";
          if (p.data.revision_limit !== null) return `${p.data.revisions_used} of ${p.data.revision_limit}`;
          return p.data.revisions_used > 0 ? `${p.data.revisions_used} (no limit)` : "";
        },
      },
      {
        headerName: "Status", field: "status", width: 150,
        valueGetter: (p) => (p.data && isOverdue(p.data) ? "overdue" : p.data?.status),
        cellClass: (p) => STATUS_COLOURS[p.value as string] ?? "",
      },
      { headerName: "Invoice", valueGetter: (p) => p.data?.invoice?.number ?? "", width: 190 },
    ],
    [money],
  );
  return (
    <div className="ag-theme-quartz w-full">
      <AgGridReact rowData={contract.milestones} columnDefs={columns} defaultColDef={defaultColDef} domLayout="autoHeight"
        getRowId={(p) => String(p.data.id)} />
    </div>
  );
}

// ---- invoice ledger with a totals row ----
interface LedgerRow {
  id: number;
  number: string;
  milestone: string;
  amount: number;
  status: string;
  due_date: string | null;
  paid_at: string | null;
  payer_url: string | null;
  _total?: boolean;
}

export function InvoiceLedger({ contract }: { contract: Contract }) {
  const money = useMoney(contract.currency);
  const rows = useMemo<LedgerRow[]>(
    () =>
      contract.milestones
        .filter((m) => m.invoice)
        .map((m) => ({
          id: m.invoice!.id,
          number: m.invoice!.number ?? "",
          milestone: m.title,
          amount: Number(m.invoice!.amount ?? 0),
          status: isOverdue(m) ? "OVERDUE" : m.invoice!.status,
          due_date: m.invoice!.due_date,
          paid_at: m.invoice!.paid_at,
          payer_url: m.invoice!.payer_url,
        })),
    [contract],
  );
  const total = rows.reduce((sum, r) => sum + Math.round(r.amount * 100), 0) / 100;
  const paid = rows.filter((r) => r.status === "PAID").reduce((sum, r) => sum + Math.round(r.amount * 100), 0) / 100;
  const totalRow: LedgerRow = { id: -1, number: "Total", milestone: `Paid ${money.format(paid)}`, amount: total, status: "", due_date: null, paid_at: null, payer_url: null, _total: true };

  const columns = useMemo<ColDef<LedgerRow>[]>(
    () => [
      { headerName: "Invoice", field: "number", flex: 1, minWidth: 190, cellClass: (p) => (p.data?._total ? "font-semibold" : "") },
      { headerName: "For", field: "milestone", flex: 2, minWidth: 180 },
      {
        headerName: "Amount", field: "amount", width: 130, type: "rightAligned", filter: "agNumberColumnFilter",
        valueFormatter: (p) => (p.value == null ? "" : money.format(p.value)),
        cellClass: (p) => (p.data?._total ? "font-semibold" : ""),
      },
      { headerName: "Status", field: "status", width: 130, cellClass: (p) => STATUS_COLOURS[String(p.value).toLowerCase()] ?? STATUS_COLOURS[p.value as string] ?? "" },
      { headerName: "Due", field: "due_date", width: 130, valueFormatter: (p) => p.value ?? "" },
      { headerName: "Paid", field: "paid_at", width: 170, valueFormatter: (p) => (p.value ? new Date(p.value).toLocaleString() : "") },
      {
        headerName: "Pay link", field: "payer_url", width: 110, sortable: false, filter: false,
        cellRenderer: (p: { value: string | null }) =>
          p.value ? <a href={p.value} target="_blank" rel="noreferrer" className="text-sky-700 underline">Open</a> : null,
      },
    ],
    [money],
  );

  if (rows.length === 0) {
    return <p className="rounded-lg border border-dashed border-slate-300 p-4 text-sm text-slate-500">No invoices yet. They appear here as soon as one is sent.</p>;
  }
  return (
    <div className="ag-theme-quartz w-full">
      <AgGridReact rowData={rows} columnDefs={columns} defaultColDef={defaultColDef} domLayout="autoHeight"
        pinnedBottomRowData={[totalRow]} getRowId={(p) => String(p.data.id)} />
    </div>
  );
}

// ---- audit log: a filterable timeline ----
const ACTORS = ["all", "user", "client", "system", "ai", "paypal"];

const summarise = (details: AuditItem["details"]) =>
  Object.entries(details).map(([k, v]) => `${k.replace(/_/g, " ")}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`).join(" · ");

export function AuditLog({ contract }: { contract: Contract }) {
  const [actor, setActor] = useState("all");
  const [search, setSearch] = useState("");
  const rows = useMemo(
    () =>
      [...contract.audit].reverse().filter((e) => actor === "all" || e.actor === actor)
        .map((e, i) => ({ id: i, at: e.at, actor: e.actor, action: e.action.replace(/_/g, " "), details: summarise(e.details) })),
    [contract.audit, actor],
  );
  const columns = useMemo<ColDef<(typeof rows)[number]>[]>(
    () => [
      { headerName: "When", field: "at", width: 190, valueFormatter: (p) => new Date(p.value).toLocaleString() },
      { headerName: "Who", field: "actor", width: 110 },
      { headerName: "What", field: "action", flex: 1, minWidth: 200 },
      { headerName: "Details", field: "details", flex: 3, minWidth: 280 },
    ],
    [],
  );
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-3 text-sm">
        <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search the log"
          className="rounded-lg border border-slate-300 px-3 py-2" />
        <select value={actor} onChange={(e) => setActor(e.target.value)} className="rounded-lg border border-slate-300 px-3 py-2">
          {ACTORS.map((a) => (
            <option key={a} value={a}>{a === "all" ? "Everyone" : a}</option>
          ))}
        </select>
      </div>
      <div className="ag-theme-quartz w-full">
        <AgGridReact rowData={rows} columnDefs={columns} defaultColDef={defaultColDef} domLayout="autoHeight"
          quickFilterText={search} getRowId={(p) => String(p.data.id)} />
      </div>
    </div>
  );
}
