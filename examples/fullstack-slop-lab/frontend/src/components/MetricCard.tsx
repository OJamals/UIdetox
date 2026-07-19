type Props = {
  icon: string;
  label: string;
  value: string;
  trend: string;
  tone?: string;
};

export function MetricCard({ icon, label, value, trend, tone = "purple" }: Props) {
  return (
    <article className={`metric-card glass-card ${tone}`}>
      <div className="icon-tile">{icon}</div>
      <div>
        <p>{label}</p>
        <strong>{value}</strong>
        <small className="positive">{trend}</small>
      </div>
    </article>
  );
}
