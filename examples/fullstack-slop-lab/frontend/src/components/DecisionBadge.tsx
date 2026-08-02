type DecisionBadgeProps = {
  state?: string;
  risk?: number;
};

export function DecisionBadge({ state, risk }: DecisionBadgeProps) {
  const loud = (risk || 0) > 60 || state?.includes("pending");
  return (
    <span className={`decision-badge ${loud ? "urgent" : "calm"}`}>
      {state || "Awaiting intelligent decision"}
      <small>{risk || "?"}% risk</small>
    </span>
  );
}
