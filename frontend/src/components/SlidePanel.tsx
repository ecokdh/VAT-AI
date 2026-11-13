import { useEffect, useRef, type PointerEvent, type ReactNode } from "react";
import "../styles/sheet.css";

// 앱 폭 안에서 아래에서 올라오는 상세 시트. 위 손잡이를 끌어내리거나 ✕·바깥·Esc로 닫는다.
export function SlidePanel({ open, label, title, onClose, children }: {
  open: boolean; label: string; title: ReactNode; onClose: () => void; children: ReactNode;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const drag = useRef<{ startY: number; dy: number } | null>(null);
  useEffect(() => {
    const panel = dialog.current;
    if (!panel) return;
    if (open && !panel.open) { panel.style.transform = ""; panel.showModal(); panel.querySelector<HTMLElement>(".sheet-scroll")?.focus(); }
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

  // 손잡이 끌기: 아래로 120px 넘게 끌면 닫고, 아니면 제자리로 돌아간다.
  function onDragStart(e: PointerEvent<HTMLDivElement>) { drag.current = { startY: e.clientY, dy: 0 }; e.currentTarget.setPointerCapture(e.pointerId); }
  function onDragMove(e: PointerEvent<HTMLDivElement>) {
    if (!drag.current || !dialog.current) return;
    drag.current.dy = Math.max(0, e.clientY - drag.current.startY);
    dialog.current.style.transform = `translateY(${drag.current.dy}px)`;
  }
  function onDragEnd() {
    if (!drag.current || !dialog.current) return;
    const far = drag.current.dy > 120;
    drag.current = null;
    dialog.current.style.transform = "";
    if (far) close();
  }

  return <dialog ref={dialog} className="sheet" aria-label={label} onClose={onClose} onCancel={e => { e.preventDefault(); close(); }}
    onClick={e => { if (e.target === e.currentTarget) close(); }}>{open && <>
    <div className="sheet-top" onPointerDown={onDragStart} onPointerMove={onDragMove} onPointerUp={onDragEnd} onPointerCancel={onDragEnd}>
      <span className="sheet-grab" aria-hidden="true" />
      <button type="button" className="sheet-close" aria-label={`${label} 닫기`} onPointerDown={e => e.stopPropagation()} onClick={close}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
      </button>
    </div>
    <div className="sheet-scroll" tabIndex={-1}><h2 className="sheet-title">{title}</h2>{children}</div>
  </>}</dialog>;
}
