import { useLayoutEffect, useRef, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import "../styles/vault-tabs.css";

// 매입·매출 보관함 탭: 이동하면 파란 선택 표시가 이전 탭 자리에서 새 탭으로 밀려 간다.
export function VaultTabs({ purchaseTo, salesTo, children }: { purchaseTo: string; salesTo: string; children?: ReactNode }) {
  const nav = useRef<HTMLElement>(null);
  const indicator = useRef<HTMLSpanElement>(null);
  const { pathname, state } = useLocation();
  const from = (state as { vaultFrom?: number } | null)?.vaultFrom;
  const current = pathname.startsWith("/storage/sales") ? 1 : 0;
  useLayoutEffect(() => {
    const tabs = nav.current?.querySelectorAll<HTMLElement>("a");
    const bar = indicator.current;
    if (!tabs || !bar) return;
    // 탭 칸보다 양옆 4px 안쪽에 그려 바깥 테두리에 붙지 않게 한다.
    const place = (tab: HTMLElement) => { bar.style.left = `${tab.offsetLeft + 4}px`; bar.style.width = `${tab.offsetWidth - 8}px`; };
    if (from != null && from !== current && tabs[from]) {
      bar.style.transition = "none";
      place(tabs[from]);
      void bar.offsetWidth; // 시작 위치를 먼저 확정해야 이동이 애니메이션된다
      bar.style.transition = "";
    }
    place(tabs[current]);
  }, [pathname, from, current]);
  return <nav ref={nav} className="vault-tabs vault-tabs--slide" aria-label="보관함 종류">
    <span ref={indicator} className="vault-tabs__indicator" aria-hidden="true" />
    <NavLink to={purchaseTo} state={{ vaultFrom: current }}>매입</NavLink>
    <NavLink to={salesTo} state={{ vaultFrom: current }}>매출</NavLink>
    {children}
  </nav>;
}
