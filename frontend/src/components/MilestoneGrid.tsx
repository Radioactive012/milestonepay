import type { CellClassParams, CellClassRules, CellValueChangedEvent, ColDef } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { useMemo } from "react";
import type { Contract, Milestone, MilestoneChanges } from "../types";

interface Props {
  contract: Contract;
  /** Saves one edit. Resolves false when the server refused it, so the grid can reset. */
  onEdit: (id: number, changes: MilestoneChanges) => Promise<boolean>;
  gridKey: number;
}

type Row = Milestone & { _total?: boolean };

export default function MilestoneGrid({ contract, onEdit, gridKey }: Props) {
  const money = useMemo(
    () => new Intl.NumberFormat(undefined, { style: "currency", currency: contract.currency || "USD" }),
    [contract.currency],
  );
  const editable = (m?: Row) => !!m && !m._total && m.status === "draft" && !m.is_deposit;

  const columns = useMemo<ColDef<Row>[]>(
    () => [
      {
        headerName: "#",
        field: "position",
        width: 70,
        editable: false,
        valueFormatter: (p) => (p.data?._total || p.data?.is_deposit ? "" : String(p.value ?? "")),
      },
      { headerName: "Milestone", field: "title", flex: 2, minWidth: 160, editable: (p) => editable(p.data) },
      {
        headerName: "Amount",
        field: "amount",
        width: 140,
        type: "rightAligned",
        editable: (p) => editable(p.data),
        valueGetter: (p) => (p.data?.amount == null ? null : Number(p.data.amount)),
        valueSetter: (p) => {
          const next = Number(p.newValue);
          if (!Number.isFinite(next) || next <= 0) return false;
          p.data.amount = next.toFixed(2);
          return true;
        },
        valueFormatter: (p) => (p.value == null ? "" : money.format(p.value)),
        cellClassRules: { "font-semibold": (p: CellClassParams<Row>) => !!p.data?._total } as CellClassRules<Row>,
      },
      {
        headerName: "Paid when",
        field: "trigger",
        width: 130,
        editable: (p) => editable(p.data),
        cellEditor: "agSelectCellEditor",
        cellEditorParams: { values: ["date", "event"] },
        valueFormatter: (p) => (p.value === "approval" ? "on approval" : (p.value ?? "")),
      },
      {
        headerName: "Due date",
        headerTooltip: "Format: YYYY-MM-DD",
        field: "due_date",
        width: 140,
        editable: (p) => editable(p.data) && p.data?.trigger === "date",
        valueFormatter: (p) => p.value ?? "",
        // Checks: a date-based milestone needs a real date before it can be approved.
        cellClassRules: {
          "bg-red-100": (p: CellClassParams<Row>) => !!p.data && !p.data._total && p.data.trigger === "date" && !p.data.due_date,
        } as CellClassRules<Row>,
      },
      { headerName: "What triggers it", field: "trigger_description", flex: 3, minWidth: 200, editable: (p) => editable(p.data) },
      { headerName: "Status", field: "status", width: 140, editable: false },
    ],
    [money], // eslint-disable-line react-hooks/exhaustive-deps
  );

  const total = contract.milestones.reduce((sum, m) => sum + Number(m.amount ?? 0), 0);
  const totalRow: Row = {
    id: -1, revisions_used: 0, position: 0, title: "Total", amount: total.toFixed(2), trigger: "", trigger_description: null,
    due_date: null, revision_limit: null, is_deposit: false, status: "", invoice: null, _total: true,
  };

  async function handleChange(event: CellValueChangedEvent<Row>) {
    const field = event.colDef.field as keyof Row;
    const id = event.data.id;
    let changes: MilestoneChanges | null = null;
    if (field === "title") changes = { title: String(event.newValue ?? "").trim() };
    if (field === "amount") changes = { amount: Number(event.data.amount) };
    if (field === "trigger") changes = { trigger: event.newValue };
    if (field === "due_date") changes = { due_date: String(event.newValue ?? "").trim() || null };
    if (field === "trigger_description") changes = { trigger_description: String(event.newValue ?? "") };
    if (!changes) return;
    if (field === "title" && !(changes as { title: string }).title) {
      await onEdit(id, { title: "" }); // the server refuses an empty title and the grid resets
      return;
    }
    await onEdit(id, changes);
  }

  return (
    <div className="ag-theme-quartz w-full">
      <AgGridReact<Row>
        key={gridKey}
        rowData={contract.milestones}
        columnDefs={columns}
        getRowId={(p) => String(p.data.id)}
        pinnedBottomRowData={[totalRow]}
        domLayout="autoHeight"
        onCellValueChanged={handleChange}
        stopEditingWhenCellsLoseFocus
      />
    </div>
  );
}
