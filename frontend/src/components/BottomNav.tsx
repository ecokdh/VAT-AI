import { useLayoutEffect, useRef, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { Icon } from "./Icon";
import { parseSalesPeriod, salesPeriodQuery } from "../hooks/salesPeriod";

export function BottomNav() {
  const { pathname, search } = useLocation();
  const navigate = useNavigate();
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
    <button className="bottom-nav__ocr" onClick={() => navigate("/capture")}><Icon name="camera"/>OCR</button>
    <NavLink to="/dashboard"><Icon name="home"/>홈</NavLink>
    <NavLink to={`/storage/${vault}${periodSuffix}`} className={pathname.startsWith("/storage") ? "active" : ""}><Icon name="folder"/>보관함</NavLink>
  </nav>;
}
