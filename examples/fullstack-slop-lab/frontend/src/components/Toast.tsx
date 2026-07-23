type Props = {
  message: string;
  onClose: () => void;
};

export function Toast({ message, onClose }: Props) {
  return (
    <div aria-live="polite" className="toast" role="status">
      <div>
        <b>Operation complete</b>
        <p>{message}</p>
      </div>
      <button aria-label="Dismiss notification" type="button" onClick={onClose}>×</button>
    </div>
  );
}
