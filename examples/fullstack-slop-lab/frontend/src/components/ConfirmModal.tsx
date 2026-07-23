import { useId } from "react";
import { ModalDialog } from "./ModalDialog";

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
  const titleId = useId();
  const messageId = useId();

  return (
    <ModalDialog
      open={open}
      labelledBy={titleId}
      describedBy={messageId}
      onClose={onClose}
    >
      <div>
        <span aria-hidden="true" className="modal-icon">!</span>
        <h2 id={titleId}>{title}</h2>
        <p id={messageId}>{message}</p>
        <div className="modal-actions">
          <button
            type="button"
            className="secondary-button"
            onClick={onClose}
          >
            Cancel
          </button>
          <button type="button" className="danger-button" onClick={onConfirm}>
            Yes, delete it
          </button>
        </div>
      </div>
    </ModalDialog>
  );
}
