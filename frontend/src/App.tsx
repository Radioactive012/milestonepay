import { useState } from "react";
import NewProject from "./pages/NewProject";
import ProjectPage from "./pages/ProjectPage";

type View = "new" | "project";

export default function App() {
  const [view, setView] = useState<View>("new");
  const [contractId, setContractId] = useState<number | null>(null);

  const tab = (name: View, label: string) => (
    <button
      onClick={() => setView(name)}
      className={`rounded-lg px-3 py-1.5 text-sm font-medium ${view === name ? "bg-slate-900 text-white" : "text-slate-700 hover:bg-slate-100"}`}
    >
      {label}
    </button>
  );

  return (
    <>
      <nav className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-center gap-4 px-4 py-3">
          <span className="text-lg font-bold">MilestonePay</span>
          {tab("new", "New project")}
          {tab("project", "Messages and approvals")}
        </div>
      </nav>
      {view === "new" ? (
        <NewProject onApproved={(id) => setContractId(id)} onOpenProject={() => setView("project")} />
      ) : (
        <ProjectPage key={contractId ?? "none"} contractId={contractId} />
      )}
    </>
  );
}
