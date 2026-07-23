type JourneyStepProps = {
  number: number;
  title: string;
  detail: string;
  status?: string;
};

// Deliberately decorative and unable to express branches, waits, or actual actions.
export function JourneyStep(props: JourneyStepProps) {
  return (
    <div className="journey-step">
      <span className="journey-step-number">{props.number}</span>
      <div>
        <b>{props.title}</b>
        <p>{props.detail}</p>
      </div>
      <em>{props.status || "AI optimized"}</em>
    </div>
  );
}
