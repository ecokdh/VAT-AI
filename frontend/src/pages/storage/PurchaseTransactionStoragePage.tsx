import { TeamBenchmarkTab } from "../../components/TeamBenchmarkTab";
import { VaultTabs } from "../../components/VaultTabs";
import { useCallback, useEffect, useRef, useState } from "react";
import { NavLink, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { getMe } from "../../api/auth";
import { isAxiosError } from "axios";
import { confirmTransaction, confirmTransactionFromReceipt, createAnalysisRun, listTransactions, moveTransactionToTrash, type TransactionApi } from "../../api/transactions";
import { listReceiptInbox, saveReceiptEdits, type ReceiptProcessingApi } from "../../api/receipts";
import { inPeriod, isPeriod, needsReview } from "../../hooks/useReviewOverview";
import { filterLedger, matchesReviewStatus, reviewLabel, reviewStatusClass } from "../../hooks/reviewState";
import { parseSalesPeriod } from "../../hooks/salesPeriod";
import { rememberPeriod, rememberedPeriod, useReturnedPeriod } from "../../hooks/currentPeriod";
import { PeriodPicker } from "../../components/PeriodPicker";
import { LedgerCard } from "../../components/LedgerCard";
import { PageHeader } from "../../components/PageHeader";
import { DeleteConfirmation } from "../../components/DeleteConfirmation";
import { ReceiptPreview } from "../../components/ReceiptPreview";
import { ReceiptDocumentDetails } from "../../components/ReceiptDocumentDetails";
import { SlidePanel } from "../../components/SlidePanel";
import { TransactionDetailSheet } from "../../components/TransactionDetailSheet";
import type { SavedDocument } from "../../components/MonthlySalesReview";
import { apiClient } from "../../api/client";
import { formatWon } from "../../utils/format";

const PREVIEW_COUNT = 5;
// 분석 대기 거래는 자동으로 분석에 포함되고, 직접 고르는 것은 애매(추가 확인 필요) 거래의 재분석뿐이다.
const isWaiting = (r: TransactionApi) => r.direction === "purchase" && matchesReviewStatus(r, "waiting");
const isSelectable = (r: TransactionApi) => r.direction === "purchase" && matchesReviewStatus(r, "caution");
export function PurchaseTransactionStoragePage({ direction = "purchase" }: { direction?: "purchase" | "sales" }) {
  const navigate = useNavigate();
  const location = useLocation();
const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "all";
  const purchase = direction === "purchase";
  const combined = purchase && params.get("scope") === "all";
  const [transactions, setTransactions] = useState<TransactionApi[]>([]);
  const [inbox, setInbox] = useState<ReceiptProcessingApi[]>([]);
  const [monthly, setMonthly] = useState<SavedDocument[]>([]);
  const [simplified, setSimplified] = useState(false);
  const requestedPeriod = params.get("period");
  const returnedPeriod = useReturnedPeriod();
  const validPeriod = returnedPeriod ?? (isPeriod(requestedPeriod) ? requestedPeriod
    : (!purchase && parseSalesPeriod(requestedPeriod)) || (requestedPeriod ? "all" : rememberedPeriod() ?? "all"));
  const period = simplified && validPeriod !== "all" ? `${validPeriod.slice(0,4)}-YEAR` : validPeriod;
  useEffect(() => { rememberPeriod(period); }, [period]);
  const [month, setMonth] = useState("");
  const [order, setOrder] = useState("newest");
  const [selected, setSelected] = useState<number[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<TransactionApi | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [detail, setDetail] = useState<TransactionApi | null>(null);
  const [resultMode, setResultMode] = useState(false);
  const [receiptDetail, setReceiptDetail] = useState<ReceiptProcessingApi | null>(null);
  const [receiptEditing, setReceiptEditing] = useState(false);
  // 월간 매출 정산서도 매입 거래처럼 상세 창에서 확인하고 휴지통으로 옮긴다.
  const [monthlyDetail, setMonthlyDetail] = useState<SavedDocument | null>(null);
  const [monthlyDelete, setMonthlyDelete] = useState<SavedDocument | null>(null);
  const monthlyName = (r: SavedDocument) => (r.document.사업장.상호 as string | null) || "월간 매출 정산서";
  const monthlyAmount = (r: SavedDocument) => typeof r.document.집계합계.실매출액 === "number" ? formatWon(r.document.집계합계.실매출액) : "금액 확인 필요";
  const openDetail = (item: TransactionApi, result = false) => { setResultMode(result); setDetail(item); };
  const [scrolled, setScrolled] = useState(false);
  const refreshRun = useRef(0);
  const refresh = useCallback(async () => {
    const run = ++refreshRun.current;
    setLoading(true);
    try {
      const [rows, receipts, monthlyDocs] = await Promise.all([combined ? Promise.all([listTransactions("purchase"),listTransactions("sales")]).then(groups=>groups.flat()) : listTransactions(direction), listReceiptInbox(), direction === 'sales' ? apiClient.get<SavedDocument[]>('/sales/monthly').then(r=>r.data) : Promise.resolve([])]);
      if(run !== refreshRun.current) return;
      setTransactions(rows); setInbox(receipts.filter(r => combined || r.direction === direction)); setMonthly(monthlyDocs);
      setSelected(ids => ids.filter(id => rows.some(r => r.id === id)));
    } catch { if(run === refreshRun.current) setMessage("거래를 불러오지 못했습니다. 다시 시도해 주세요."); }
    finally { if(run === refreshRun.current) setLoading(false); }
  }, [direction, combined]);
  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => { getMe().then(user => setSimplified(user.business?.tax_type_code === "02")).catch(() => {}); }, []);
  useEffect(() => { const scroll = () => setScrolled(window.scrollY > 300); window.addEventListener("scroll", scroll); return () => window.removeEventListener("scroll", scroll); }, []);
  const periodRows = transactions.filter(r => period === "all" || inPeriod(r.transaction_date, period));
  const periodInbox = inbox.filter(r => period === "all" || !r.date || inPeriod(r.date, period));
  const periodMonthly=monthly.filter(r=>{const m=r.document.거래일;return period==='all'||!m||(/^\d{4}-\d{2}$/.test(m)&&inPeriod(`${m}-01`,period));});
  // 확인 저장한 정산서(reviewed)는 매출 합계에 들어가고, 저장 전 정산서만 확인 필요로 센다.
  const reviewedMonthly = periodMonthly.filter(r=>r.status === 'reviewed');
  const review = periodRows.filter(needsReview).length + periodInbox.length + periodMonthly.length - reviewedMonthly.length;
  const total = periodRows.length + periodInbox.length + periodMonthly.length;
  const { transactions: filtered, receipts } = filterLedger(periodRows, periodInbox, { period: "all", month, status, order });
  const monthlyVisible=periodMonthly.filter(r=>(status === 'all' || (status === 'done') === (r.status === 'reviewed'))&&(!month||!r.document.거래일||Number(r.document.거래일.slice(5,7))===Number(month)));
  const shownReceipts = receipts.slice(0, PREVIEW_COUNT);
  const shownRows = filtered.slice(0, PREVIEW_COUNT - shownReceipts.length);
  const hiddenCount = receipts.length + filtered.length - shownReceipts.length - shownRows.length;
  const visibleSelected = selected.filter(id => filtered.some(r => r.id === id && isSelectable(r)));
  // 추가 확인 필요 탭에서는 고른 거래만 다시 분석하고, 분석 대기 거래는 분석 대기 탭에서만 함께 분석한다.
  const includeWaiting = status === "waiting";
  const waitingRows = includeWaiting ? periodRows.filter(isWaiting) : [];
  const waitingReceipts = includeWaiting ? periodInbox.filter(r => r.direction === "purchase") : [];
  const waitingCount = waitingRows.length + waitingReceipts.length;
  const analyzeTab = ["waiting", "caution"].includes(status);
  const judgedTab = ["deductible", "nondeductible"].includes(status);
  function updateFilters(next: {period?:string;status?:string}) {setParams({...Object.fromEntries(params),...next},{replace:true});setSelected([]);}
  function filter(value:string) {updateFilters({status:value});}
  // 분석 대기(영수증·미확정 포함)는 모두, 애매 거래는 선택한 것만 한 번에 분석한다.
  async function analyzeAll() {
    if (busy || !(waitingCount + visibleSelected.length)) return;
    setBusy(true); setMessage("");
    const ids = [...waitingRows.filter(r => r.state === "confirmed").map(r => r.id), ...visibleSelected], failed: string[] = [];
    const convert = async (name: string, load: () => Promise<TransactionApi>) => { try { ids.push((await load()).id); } catch { failed.push(name); } };
    for (const r of waitingReceipts) await convert(r.vendor || "영수증", () => confirmTransactionFromReceipt(r.id));
    for (const r of waitingRows.filter(r => r.state !== "confirmed")) await convert(r.description || r.vendor, () => confirmTransaction(r.id));
    const unique = [...new Set(ids)].slice(0, 100);
    const note = failed.length ? `${failed.join(", ")}은(는) 거래 정보를 확인할 수 없어 분석에서 제외했습니다.` : "";
    try {
      if (!unique.length) { await refresh(); setMessage(note || "분석할 거래가 없습니다."); return; }
      const run = await createAnalysisRun(unique); navigate(`/analysis/${run.id}`, { state: { from: location.pathname + location.search } });
    } catch { setMessage("분석 작업을 시작하지 못했습니다. 잠시 후 다시 시도해 주세요."); }
    finally { setBusy(false); }
  }
  async function remove() {
    if ((!deleteTarget && !monthlyDelete) || deleting) return;
    setDeleting(true);
    try {
      if (monthlyDelete) await apiClient.post(`/sales/monthly/${monthlyDelete.id}/trash`); else if (deleteTarget) await moveTransactionToTrash(deleteTarget.id);
      setDeleteTarget(null); setMonthlyDelete(null); setDetail(null); setMonthlyDetail(null); await refresh(); setMessage("휴지통으로 옮겼습니다. 휴지통에서 복원할 수 있어요."); }
    catch { setDeleteError("삭제하지 못했습니다. 다시 시도해 주세요."); }
    finally { setDeleting(false); }
  }
  // 영수증·미확정 거래는 별도 확인 단계 없이 거래로 확정한 뒤 바로 상세를 연다.
  async function openAsTransaction(load: () => Promise<TransactionApi>) {
    if (busy) return;
    setBusy(true); setMessage("");
    try { const transaction = await load(); await refresh(); openDetail(transaction); }
    catch (cause) { setMessage((isAxiosError(cause) && cause.response?.data?.error?.message) || "거래 상세 정보를 열지 못했습니다. 다시 시도해 주세요."); }
    finally { setBusy(false); }
  }
  return <div className="page qa-page"><PageHeader title={combined ? "확인할 거래" : purchase ? "매입 보관함" : "매출 보관함"} /><main className="page__body">
    <p className="eyebrow muted">{purchase ? "매입 증빙 및 공제 분석" : "매출 증빙 및 거래 관리"}</p><h1 className="screen-title">{combined ? "매입·매출을 함께 확인하세요" : purchase ? "내 매입 거래를 관리하세요" : "내 매출 내역을 확인하세요"}</h1>
    <VaultTabs purchaseTo={`/storage/purchase?period=${period}`} salesTo={`/storage/sales?period=${period}`}><TeamBenchmarkTab /></VaultTabs>
    <PeriodPicker value={period} simplified={simplified} allowAll onChange={period=>updateFilters({period})}/>
    {combined && <p className="banner banner--info">홈 요약에서 선택한 매입·매출 거래를 함께 표시합니다.</p>}
    <div className="stat-grid stat-filters">{[["all","전체 거래",total],["review","확인 필요",review],["done",purchase ? "분석 완료" : "확정 거래",total-review]].map(([key,label,count]) => <button key={key} aria-pressed={status === key} onClick={() => filter(String(key))}><small>{label}</small><strong>{count}건</strong></button>)}</div>
    {!purchase && <p className="banner banner--info">보관된 증빙 목록입니다. <NavLink to={`/storage/sales?period=${period}`}>신고용 매출 확인</NavLink>에서 홈택스 집계를 확인하세요.</p>}
    {message && <p className="banner banner--info" role="status">{message}</p>}
    <div className="section-heading"><h2 className="section-title">거래 목록</h2><select className="sort-select" aria-label="거래 정렬" value={order} onChange={e=>setOrder(e.target.value)}><option value="newest">최신순</option><option value="oldest">오래된순</option><option value="amount">금액순</option></select></div>
    <div className="month-filter" aria-label="거래 월"><button aria-pressed={!month} onClick={()=>{setMonth("");setSelected([]);}}>전체</button>{Array.from({length:12},(_,i)=>String(i+1)).map(m=><button key={m} aria-pressed={month===m} onClick={()=>{setMonth(m);setSelected([]);}}>{m}월</button>)}</div>
    <div className="status-tabs">{(purchase ? [["all","전체"],["waiting","분석 대기"],["caution","추가 확인 필요"],["deductible","공제"],["nondeductible","불공제"]] : [["all","전체"],["review","확인 필요"],["done","확정"]]).map(([key,label])=><button key={key} aria-pressed={status===key} onClick={()=>filter(key)}>{label}</button>)}</div>
    {loading ? <p className="center-note" role="status">거래를 불러오는 중입니다.</p> : <>
      {!filtered.length && !receipts.length && !monthlyVisible.length && <div className="empty-card"><strong>표시할 거래가 없어요</strong><p className="muted">신고 기간·월·상태를 바꾸거나 증빙을 추가해 주세요.</p></div>}
      {monthlyVisible.map(r=><LedgerCard key={`monthly-${r.id}`} title={monthlyName(r)} date={r.document.거래일 || "거래월 확인 필요"} amount={monthlyAmount(r)}
        status={r.status === 'reviewed' ? '증빙 확인 완료' : '증빙 확인 필요'} statusClass={r.status === 'reviewed' ? 'status-label--done' : 'status-label--review'} onDetail={()=>setMonthlyDetail(r)} />)}
      {shownReceipts.map(r=><LedgerCard key={`receipt-${r.id}`} title={r.vendor || "거래처 확인 필요"} date={`${r.date ?? "거래일 확인 필요"}${combined ? ` · ${r.direction === "sales" ? "매출" : "매입"}` : ""}`}
        amount={r.amount == null ? "금액 확인 필요" : formatWon(r.amount)} status="분석 대기" statusClass="status-label--wait" detailDisabled={busy} onDetail={()=>void openAsTransaction(()=>confirmTransactionFromReceipt(r.id))} />)}
      {shownRows.map(item=>{const waiting = isWaiting(item); return <LedgerCard key={item.id}
        select={isSelectable(item) && <input type="checkbox" aria-label={`${item.description || item.vendor} 분석 선택`} checked={visibleSelected.includes(item.id)} onChange={e=>setSelected(ids=>e.target.checked?[...ids,item.id]:ids.filter(id=>id!==item.id))}/>}
        title={item.description || item.vendor} date={`${item.transaction_date}${combined ? ` · ${item.direction === "sales" ? "매출" : "매입"}` : ""}`} amount={formatWon(item.total_amount)}
        status={waiting ? "분석 대기" : reviewLabel(item)} statusClass={waiting ? "status-label--wait" : reviewStatusClass(item)} detailDisabled={busy}
        onDetail={()=>item.state !== "confirmed" ? void openAsTransaction(()=>confirmTransaction(item.id)) : openDetail(item)}
        // 분석 결과 칸은 분석이 끝난 매입 거래만 둔다. 매출은 '상세 ›'로 본다.
        result={!waiting && item.state === "confirmed" && item.direction === "purchase" ? { kind: needsReview(item) ? "review" : item.review_status === "excluded" ? "nondeductible" : "deductible", onClick: () => openDetail(item, true) } : undefined} />;})}
      {hiddenCount > 0 && <button type="button" className="btn btn--secondary view-all" onClick={()=>navigate(`/storage/${direction}/receipts?${new URLSearchParams({ period, month, status, order })}`)}>전체 보기 ({receipts.length + filtered.length}건)</button>}
    </>}
    {!(purchase && judgedTab) && <div className="vault-actions">{purchase && analyzeTab && <><p className="muted">{includeWaiting ? `분석 대기 ${waitingCount}건` : `다시 분석할 거래 ${visibleSelected.length}건`}</p><button className="btn btn--primary" disabled={!(waitingCount + visibleSelected.length) || busy} onClick={()=>void analyzeAll()}>{busy?"분석 준비 중":"거래 분석하기"}</button></>}<button className="btn btn--secondary" onClick={()=>navigate(`/capture?direction=${direction}`)}>＋ {purchase?"매입":"매출"} 증빙 추가</button></div>}
    <div className="section-heading utility-row"><button className="text-link" onClick={()=>navigate(`/storage/trash?direction=${direction}`)}>휴지통</button><button className="text-link" disabled={loading} onClick={()=>void refresh()}>새로고침</button></div>
    <p className="footnote">{purchase ? "거래 정보를 확인·확정한 후 세액 계산에 반영합니다." : "신고용 매출은 홈택스 매출 검증 화면에서 관리합니다."}</p>
  </main>
  {scrolled && <button className="scroll-top" aria-label="맨 위로 이동" onClick={()=>window.scrollTo({top:0,behavior:"smooth"})}>↑</button>}
  {(deleteTarget || monthlyDelete) && <DeleteConfirmation name={monthlyDelete ? monthlyName(monthlyDelete) : deleteTarget ? deleteTarget.description || deleteTarget.vendor : ""} busy={deleting} error={deleteError} onCancel={()=>{setDeleteTarget(null);setMonthlyDelete(null);}} onConfirm={()=>void remove()} />}
  <SlidePanel open={!!monthlyDetail} label="정산서 상세" title={monthlyDetail ? monthlyName(monthlyDetail) : ""} onClose={()=>setMonthlyDetail(null)}>{monthlyDetail && <><p>{monthlyDetail.document.거래일 || "거래월 확인 필요"} · 월간 매출 정산서</p><div className="peek-amount-row"><strong className="peek-amount">{monthlyAmount(monthlyDetail)}</strong><button type="button" className="text-link" onClick={()=>navigate(`/receipts/monthly/${monthlyDetail.id}/review`)}>수정하기</button></div>
    <p className={`status-label ${monthlyDetail.status === 'reviewed' ? 'status-label--done' : 'status-label--review'}`}>{monthlyDetail.status === 'reviewed' ? '증빙 확인 완료' : '증빙 확인 필요'}</p>
    <div className="field-row"><span>사업자등록번호</span><span>{monthlyDetail.document.사업장.사업자등록번호 ?? "확인 필요"}</span></div>
    <ReceiptPreview id={monthlyDetail.id} monthly controls/>
    <button type="button" className="text-link danger" onClick={()=>{setDeleteError("");setMonthlyDelete(monthlyDetail);}}>거래 삭제</button></>}</SlidePanel>
  <TransactionDetailSheet transaction={detail} resultMode={resultMode} onClose={()=>setDetail(null)} onSaved={()=>void refresh()} onDelete={t=>{setDeleteError("");setDeleteTarget(t);}}
    onUpdated={updated=>{setDetail(updated);setTransactions(rows=>rows.map(r=>r.id===updated.id?updated:r));}} />
  <SlidePanel open={!!receiptDetail} label="영수증 상세" title={receiptDetail?.vendor || "영수증"} onClose={()=>setReceiptDetail(null)}>{receiptDetail && <><p>{receiptDetail.date ?? "거래일 확인 필요"} · {receiptDetail.vendor}</p><div className="peek-amount-row"><strong className="peek-amount">{receiptDetail.amount == null ? "금액 확인 필요" : formatWon(receiptDetail.amount)}</strong><button type="button" className="text-link" onClick={()=>setReceiptEditing(v=>!v)}>{receiptEditing ? "수정 취소" : "수정하기"}</button></div><p className="status-label status-label--review">분석 대기</p><ReceiptPreview id={receiptDetail.id} controls/><ReceiptDocumentDetails receiptId={receiptDetail.id} edit={receiptEditing ? { save: (doc, details, receipt) => saveReceiptEdits(receipt, doc, details).then(setReceiptDetail), onCancel: () => setReceiptEditing(false), onSaved: () => { setReceiptEditing(false); void refresh(); } } : undefined}/></>}</SlidePanel></div>;
}
