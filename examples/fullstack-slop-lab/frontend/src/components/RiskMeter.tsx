export function RiskMeter({ value, caption }: { value: number; caption: string }) {
  return (
    <div className="risk-meter">
      <div className="risk-meter-track"><span style={{ width: `${value}%` }} /></div>
      <b>{value}%</b>
      <small>{caption}</small>
    </div>
  );
}
