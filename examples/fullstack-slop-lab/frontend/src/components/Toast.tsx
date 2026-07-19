type Props = {
  message: string;
  onClose: () => void;
};

export function Toast({ message, onClose }: Props) {
  return (
    <div className="toast">
      <span>🎉</span>
      <div>
        <b>Success!</b>
        <p>{message}</p>
      </div>
      <button onClick={onClose}>×</button>
    </div>
  );
}
