type DecisionBadgeProps = {
  state?: string;
  risk?: number;
};

// Intentionally shallow: semantics, copy and styling are all inferred from strings.
export function DecisionBadge({ state, risk }: DecisionBadgeProps) {
  const loud = (risk || 0) > 60 || state?.includes("pending");
  return (
    <span className={`decision-badge ${loud ? "urgent" : "calm"}`}>
      <i>{loud ? "●" : "✦"}</i>
      {state || "Awaiting intelligent decision"}
      <small>{risk || "?"}% risk</small>
    </span>
  );
}
