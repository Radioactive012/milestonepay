import { useState } from "react";
import { USE_FIXTURES } from "./api";
import Dashboard from "./pages/Dashboard";
import DemoBar, { takeDraftToOpen } from "./pages/demo/DemoBar";
import NewProject from "./pages/NewProject";
import ProjectPage from "./pages/ProjectPage";

type View = "dashboard" | "new" | "project";

export default function App() {
  const [draftId] = useState(takeDraftToOpen);
  const [view, setView] = useState<View>(draftId ? "new" : "dashboard");
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
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-2 px-4 py-3">
          <span className="mr-2 text-lg font-bold">MilestonePay</span>
          {tab("dashboard", "Dashboard")}
          {tab("new", "New project")}
          {tab("project", "Messages and approvals")}
        </div>
      </nav>
      {!USE_FIXTURES && <DemoBar />}
      {view === "dashboard" && (
        <Dashboard
          onNewProject={() => setView("new")}
          onOpenInbox={() => setView("project")}
          onOpenProject={(id) => {
            setContractId(id);
            setView("project");
          }}
        />
      )}
      {view === "new" && <NewProject draftId={draftId} onApproved={(id) => setContractId(id)} onOpenProject={() => setView("project")} />}
      {view === "project" && <ProjectPage key={contractId ?? "none"} contractId={contractId} />}
    </>
  );
}
