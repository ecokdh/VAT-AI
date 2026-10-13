import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { getMe, type AuthUser } from "../api/auth";
import { listReceiptInbox, type ReceiptProcessingApi } from "../api/receipts";
import { getTaxEstimate, listTransactions, type TaxEstimateApi, type TransactionApi } from "../api/transactions";

import { defaultPeriod, isPeriod, summarizeReview } from "./reviewState";
export { periodLabel, periodOptions, inPeriod, isPeriod, defaultPeriod, needsReview } from "./reviewState";

export function useReviewOverview() {
  const [params, setParams] = useSearchParams();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [rows, setRows] = useState<TransactionApi[]>([]);
  const [inbox, setInbox] = useState<ReceiptProcessingApi[]>([]);
  const [period, setPeriodValue] = useState(() => { const value = params.get("period"); return isPeriod(value) ? value : defaultPeriod(); });
  function setPeriod(value: string) { setPeriodValue(value); setParams({period:value}, {replace:true}); }
  const [estimate, setEstimate] = useState<TaxEstimateApi | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    Promise.all([getMe(), listTransactions("purchase"), listTransactions("sales"), listReceiptInbox()]).then(([account, purchases, sales, receipts]) => {
      if (!active) return;
      setUser(account); setRows([...purchases, ...sales]); setInbox(receipts);
      if (account.business?.tax_type_code === "02") setPeriodValue("2026-YEAR");
    }).catch(() => { if (active) setError("정보를 불러오지 못했습니다. 새로고침 후 다시 확인해 주세요."); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    let active = true;
    if (user && ["01", "02"].includes(user.business?.tax_type_code ?? "")) {
      getTaxEstimate(period).then(value => { if (active) setEstimate(value); }).catch(() => { if (active) setError("예상 세액을 불러오지 못했습니다."); });
    }
    return () => { active = false; };
  }, [user, period]);
  return { user, period, setPeriod, estimate: estimate?.period === period ? estimate : null, loading, error, ...summarizeReview(rows, inbox, period) };
}
