import { useEffect, useRef, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { Icon } from "./Icon";

export function BottomNav() {
  const location = useLocation();
  const { pathname, search } = location;
  const navigate = useNavigate();
  const [openedAt, setOpenedAt] = useState<string | null>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const nav = useRef<HTMLElement>(null);
  const open = openedAt === location.key;
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => { if (!nav.current?.contains(event.target as Node)) setOpenedAt(null); };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") { setOpenedAt(null); trigger.current?.focus(); } };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("pointerdown", outside); document.removeEventListener("keydown", escape); };
  }, [open]);
  const vault = pathname === "/storage/sales" || (pathname === "/storage/trash" && new URLSearchParams(search).get("direction") === "sales") ? "sales" : "purchase";
  if (!["/dashboard", "/storage", "/account", "/about", "/reports"].some(path => pathname.startsWith(path))) return null;
  return <nav ref={nav} className="bottom-nav" aria-label="주요 메뉴">
    <button ref={trigger} className={`bottom-nav__ocr ${open ? "active" : ""}`} aria-expanded={open} aria-controls="ocr-direction-picker" onClick={() => setOpenedAt(open ? null : location.key)}><Icon name="camera"/>OCR</button>
    <div className={`ocr-picker ${open ? "ocr-picker--open" : ""}`} id="ocr-direction-picker" role="group" aria-label="증빙 종류 선택" inert={!open} aria-hidden={!open}>
      {([['purchase', '매입', '사업에 쓴 지출'], ['sales', '매출', '고객에게 판매']] as const).map(([direction, title, description]) => <button key={direction} onClick={() => { setOpenedAt(null); navigate(`/capture?direction=${direction}`); }}><Icon name="folder"/><strong>{title}</strong><small>{description}</small></button>)}
    </div>
    <NavLink to="/dashboard" onClick={() => setOpenedAt(null)}><Icon name="home"/>홈</NavLink>
    <NavLink to={`/storage/${vault}`} onClick={() => setOpenedAt(null)} className={pathname.startsWith("/storage") ? "active" : ""}><Icon name="folder"/>보관함</NavLink>
  </nav>;
}
