export function Spinner({ label = "Loading..." }: { label?: string }) {
  return (
    <div className="loading-state">
      <span className="spinner">✨</span>
      <p>{label}</p>
    </div>
  );
}
