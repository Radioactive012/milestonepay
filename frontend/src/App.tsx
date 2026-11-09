import NewProject from "./pages/NewProject";

export default function App() {
  return (
    <>
      <nav className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-center px-4 py-3 text-lg font-bold">MilestonePay</div>
      </nav>
      <NewProject />
    </>
  );
}
