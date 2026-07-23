import { type ReactNode, useEffect, useRef } from "react";

type Props = {
  open: boolean;
  labelledBy: string;
  describedBy?: string;
  className?: string;
  children: ReactNode;
  onClose: () => void;
};

export function ModalDialog({
  open,
  labelledBy,
  describedBy,
  className = "",
  children,
  onClose,
}: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog || !open) return;

    dialog.showModal();
    return () => {
      if (dialog.open) dialog.close();
    };
  }, [open]);

  if (!open) return null;

  return (
    <dialog
      ref={dialogRef}
      aria-describedby={describedBy}
      aria-labelledby={labelledBy}
      className={`modal-card ${className}`.trim()}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      {children}
    </dialog>
  );
}
