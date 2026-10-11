import { useEffect, useRef } from "react";

export function DeleteConfirmation({ name, busy, error, onCancel, onConfirm }: {
  name: string; busy: boolean; error: string; onCancel: () => void; onConfirm: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { dialog.current?.showModal(); }, []);
  return <dialog ref={dialog} className="delete-confirmation" aria-labelledby="delete-title" aria-describedby="delete-description"
    onCancel={(event) => { event.preventDefault(); if (!busy) onCancel(); }}>
    <h2 id="delete-title">정말 삭제하실 거예요?</h2>
    <p className="delete-confirmation__name">{name}</p>
    <p id="delete-description" className="muted">거래를 휴지통으로 옮깁니다. 예상 세액 집계에서 제외되며, 휴지통에서 다시 복원할 수 있어요.</p>
    {error && <p className="banner banner--error" role="alert">{error}</p>}
    <div className="btn-row"><button autoFocus className="btn btn--secondary" disabled={busy} onClick={onCancel}>취소</button><button className="btn delete-confirmation__submit" disabled={busy} onClick={onConfirm}>{busy ? "이동 중…" : "휴지통으로 이동"}</button></div>
  </dialog>;
}
