import { useNavigationType } from "react-router-dom";
import { isPeriod } from "./reviewState";

// 대시보드·매입·매출 보관함이 마지막으로 고른 신고 대상 기간을 함께 쓴다.
const KEY = "vat-ai-period";

export function rememberedPeriod() {
  try { const value = sessionStorage.getItem(KEY); return isPeriod(value) ? value : null; } catch { return null; }
}

export function rememberPeriod(period: string) {
  if (!isPeriod(period)) return;
  try { sessionStorage.setItem(KEY, period); } catch { /* 저장할 수 없으면 주소의 기간만 쓴다 */ }
}

// 뒤로가기로 돌아온 화면은 주소에 남은 옛 기간 대신 마지막에 고른 기간을 보여준다.
export function useReturnedPeriod() {
  return useNavigationType() === "POP" ? rememberedPeriod() : null;
}
