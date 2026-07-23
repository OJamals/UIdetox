export function Spinner({ label = "Loading workspace data…" }: { label?: string }) {
  return (
    <div aria-live="polite" className="loading-state" role="status">
      <span aria-hidden="true" className="spinner" />
      <p>{label}</p>
    </div>
  );
}
