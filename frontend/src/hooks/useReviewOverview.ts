import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { getMe, type AuthUser } from "../api/auth";
import { listReceiptInbox, type ReceiptProcessingApi } from "../api/receipts";
import { getFilingReadiness, getTaxEstimate, listTransactions, type FilingReadiness, type TaxEstimateApi, type TransactionApi } from "../api/transactions";
import { defaultPeriod, isPeriod, summarizeReview, inPeriod } from "./reviewState";
export { periodLabel, periodOptions, inPeriod, isPeriod, defaultPeriod, needsReview } from "./reviewState";

export function useReviewOverview() {
 const [params,setParams]=useSearchParams();
 const requested=params.get("period");
 const period=isPeriod(requested)?requested:defaultPeriod();
 const setPeriod=(value:string)=>setParams({period:value},{replace:true});
 const [user,setUser]=useState<AuthUser|null>(null);
 const [rows,setRows]=useState<TransactionApi[]>([]);
 const [inbox,setInbox]=useState<ReceiptProcessingApi[]>([]);
 const [estimate,setEstimate]=useState<TaxEstimateApi|null>(null);
 const [readiness,setReadiness]=useState<FilingReadiness|null>(null);
 const [loading,setLoading]=useState(true);
 const [error,setError]=useState("");
 useEffect(()=>{
  let active=true; setLoading(true); setError("");
  Promise.all([getMe(),listTransactions("purchase"),listTransactions("sales"),listReceiptInbox()]).then(async ([account,purchases,sales,receipts])=>{
   if(!active)return;
   setUser(account);setRows([...purchases,...sales]);setInbox(receipts);
   if(account.business?.tax_type_code==="02" && !period.endsWith("YEAR")) {setParams({period:`${period.slice(0,4)}-YEAR`},{replace:true});return;}
   const [checks,tax]=await Promise.all([getFilingReadiness(period),["01","02"].includes(account.business?.tax_type_code??"")?getTaxEstimate(period):Promise.resolve(null)]);
   if(active){setReadiness(checks);setEstimate(tax);}
  }).catch(()=>{if(active)setError("정보를 불러오지 못했습니다. 새로고침 후 다시 확인해 주세요.");}).finally(()=>{if(active)setLoading(false);});
  return()=>{active=false;};
 },[period,setParams]);
 const summary=summarizeReview(rows,inbox,period);
 const current=readiness?.period===period?readiness:null;
 return {user,period,setPeriod,estimate:estimate?.period===period?estimate:null,loading,error,readiness:current,
  transactions:rows.filter(r=>!r.deleted_at&&inPeriod(r.transaction_date,period)),
  receipts:inbox.filter(r=>!r.date||inPeriod(r.date,period)),...summary,
  total:current?.total??summary.total,unconfirmed:current?.unconfirmed??summary.unconfirmed,pending:current?.pending??summary.pending};
}
