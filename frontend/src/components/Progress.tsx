// Shown while the AI or PayPal is working, so a slow call doesn't look like a frozen page.
export default function Progress({ children }: { children: string }) {
  return (
    <div role="status" aria-live="polite"
      className="flex items-center gap-3 rounded-lg border border-sky-200 bg-sky-50 p-3 text-sm text-sky-900">
      <span className="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-sky-300 border-t-sky-700" aria-hidden="true" />
      {children}
    </div>
  );
}
