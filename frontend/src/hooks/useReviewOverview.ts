import { useEffect, useState } from "react";
import { listReceiptInbox, type ReceiptProcessingApi } from "../api/receipts";
import { getTaxEstimate, listTransactions, type TaxEstimateApi, type TransactionApi } from "../api/transactions";
import { useFilingPeriod } from "./useFilingPeriod";
import { summarizeReview } from "./reviewState";
export { periodLabel, inPeriod, needsReview } from "./reviewState";

export function useReviewOverview() {
  const filing = useFilingPeriod();
  const [rows, setRows] = useState<TransactionApi[]>([]);
  const [inbox, setInbox] = useState<ReceiptProcessingApi[]>([]);
  const [estimate, setEstimate] = useState<TaxEstimateApi | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    Promise.all([listTransactions("purchase"), listTransactions("sales"), listReceiptInbox()]).then(([purchases, sales, receipts]) => {
      if (active) { setRows([...purchases,...sales]); setInbox(receipts); }
    }).catch(() => { if (active) setError("거래를 불러오지 못했습니다."); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    let active = true;
    if (filing.period && filing.verifiedType) {
      getTaxEstimate(filing.period).then(value => { if (active) {setEstimate(value);setError("");} }).catch(() => { if (active) setError("예상세액을 불러오지 못했습니다. 사업자정보와 과세유형을 확인해 주세요."); });
    }
    return () => { active = false; };
  }, [filing.period, filing.verifiedType]);
  return {...filing, estimate:filing.period && estimate?.period === filing.period ? estimate : null, loading:loading || filing.loading, error:error || filing.error, ...summarizeReview(rows,inbox,filing.period)};
}
