type Props = {
  open: boolean;
  title: string;
  message: string;
  onConfirm: () => void;
  onClose: () => void;
};

export function ConfirmModal({
  open,
  title,
  message,
  onConfirm,
  onClose,
}: Props) {
  if (!open) return null;

  return (
    <div className="modal-backdrop">
      <div className="modal-card glass-card">
        <span className="modal-icon">⚠️</span>
        <h2>{title}</h2>
        <p>{message}</p>
        <div className="modal-actions">
          <button className="secondary-button" onClick={onClose}>
            Cancel
          </button>
          <button className="danger-button" onClick={onConfirm}>
            Yes, delete it
          </button>
        </div>
      </div>
    </div>
  );
}

