import { NavLink, useLocation } from "react-router-dom";
import { Icon } from "./Icon";

export function BottomNav() {
  const { pathname, search } = useLocation();
  const vault = pathname === "/storage/sales" || (pathname === "/storage/trash" && new URLSearchParams(search).get("direction") === "sales") ? "sales" : "purchase";
  if (!["/dashboard", "/storage", "/account", "/about"].some((path) => pathname.startsWith(path))) return null;
  return <nav className="bottom-nav" aria-label="주요 메뉴">
    <NavLink to="/capture"><Icon name="camera" />OCR</NavLink>
    <NavLink to="/dashboard"><Icon name="home" />홈</NavLink>
    <NavLink to={`/storage/${vault}`} className={pathname.startsWith("/storage") ? "active" : ""}><Icon name="folder" />보관함</NavLink>
  </nav>;
}
