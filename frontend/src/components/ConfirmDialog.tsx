import { useEffect, useRef, type ReactNode } from "react";

export function ConfirmDialog({open, title, children, confirmLabel, cancelLabel = "취소", confirmClassName = "btn--danger", busy = false, onCancel, onConfirm}: {
  open: boolean; title: string; children?: ReactNode; confirmLabel: string; cancelLabel?: string; confirmClassName?: string; busy?: boolean;
  onCancel: () => void; onConfirm: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { if (open) dialog.current?.showModal(); else dialog.current?.close(); }, [open]);
  return <dialog ref={dialog} className="confirmation-dialog" aria-labelledby="confirmation-title" onCancel={e => {e.preventDefault(); if (!busy) onCancel();}}>
    <h2 id="confirmation-title">{title}</h2>{children && <div className="muted">{children}</div>}
    <div className="btn-row"><button type="button" className="btn btn--secondary" autoFocus disabled={busy} onClick={onCancel}>{cancelLabel}</button>
      <button type="button" className={`btn ${confirmClassName}`} disabled={busy} onClick={onConfirm}>{busy ? "처리 중…" : confirmLabel}</button></div>
  </dialog>;
}
