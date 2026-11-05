import { useLayoutEffect } from "react";
import { useLocation } from "react-router-dom";

// 화면이 바뀌면(뒤로가기 포함) 항상 맨 위에서 시작한다. 같은 화면의 필터 변경(쿼리)은 유지한다.
if (typeof window !== "undefined" && "scrollRestoration" in window.history) window.history.scrollRestoration = "manual";

export function ScrollToTop() {
  const { pathname } = useLocation();
  useLayoutEffect(() => { window.scrollTo(0, 0); }, [pathname]);
  return null;
}
