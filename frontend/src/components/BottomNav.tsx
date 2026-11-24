import { useLayoutEffect, useRef, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { Icon } from "./Icon";
import { parseSalesPeriod, salesPeriodQuery } from "../hooks/salesPeriod";
import { purchaseOcrSelectionPath } from "../hooks/purchaseOcrRoute";

export function BottomNav() {
  const { pathname, search } = useLocation();
  const nav = useRef<HTMLElement>(null);
  // 홈·보관함 중 현재 화면 뒤로 연한 배경이 미끄러져 옮겨간다.
  const [indicator, setIndicator] = useState<{ left: number; width: number } | null>(null);
  useLayoutEffect(() => {
    const active = nav.current?.querySelector<HTMLElement>("a.active");
    setIndicator(active ? { left: active.offsetLeft, width: active.offsetWidth } : null);
  }, [pathname]);
  const params = new URLSearchParams(search);
  const vault = pathname.startsWith("/storage/sales") || (pathname === "/storage/trash" && params.get("direction") === "sales") ? "sales" : "purchase";
  const period = vault === "sales" ? parseSalesPeriod(params.get("period")) : undefined;
  const periodSuffix = period ? `?${salesPeriodQuery(period)}` : "";
  if (!["/dashboard", "/storage", "/account", "/about", "/reports"].some(path => pathname.startsWith(path))) return null;
  return <nav ref={nav} className="bottom-nav" aria-label="주요 메뉴">
    {indicator && <span className="bottom-nav__indicator" style={indicator} aria-hidden="true" />}
    <Link className="bottom-nav__ocr" to={purchaseOcrSelectionPath}><Icon name="camera"/>OCR</Link>
    <NavLink to="/dashboard"><Icon name="home"/>홈</NavLink>
    <NavLink to={`/storage/${vault}${periodSuffix}`} className={pathname.startsWith("/storage") ? "active" : ""}><Icon name="folder"/>보관함</NavLink>
  </nav>;
}
