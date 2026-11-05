import { useEffect, useRef, type ReactNode } from "react";

// 오른쪽(모바일은 아래)에서 밀려 들어오는 상세 패널. 왼쪽 가장자리의 회색 화살표로 밀어서 닫는다.
export function SlidePanel({ open, label, title, onClose, children }: {
  open: boolean; label: string; title: ReactNode; onClose: () => void; children: ReactNode;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const panel = dialog.current;
    if (!panel) return;
    if (open && !panel.open) { panel.showModal(); panel.querySelector<HTMLElement>(".peek-scroll")?.focus(); }
    else if (!open && panel.open) panel.close();
  }, [open]);

  function close() {
    const panel = dialog.current;
    if (!panel || panel.classList.contains("is-closing")) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) { panel.close(); return; }
    const done = (e: AnimationEvent) => {
      if (e.target !== panel || e.pseudoElement) return;
      panel.removeEventListener("animationend", done);
      panel.classList.remove("is-closing");
      panel.close();
    };
    panel.addEventListener("animationend", done);
    panel.classList.add("is-closing");
  }

  return <dialog ref={dialog} className="analysis-peek analysis-peek--handle" aria-label={label} onClose={onClose} onCancel={e => { e.preventDefault(); close(); }}>{open && <>
    <button type="button" className="peek-handle" aria-label={`${label} 닫기`} onClick={close}><svg viewBox="0 0 24 24" aria-hidden><circle cx="12" cy="12" r="10.5" /><path d="M10 7.5 14.5 12 10 16.5" /></svg></button>
    <div className="peek-scroll" tabIndex={-1}><h2 className="peek-title">{title}</h2>{children}</div></>}</dialog>;
}
