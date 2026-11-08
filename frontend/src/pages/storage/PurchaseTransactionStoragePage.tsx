import {TransactionQuestions} from "../../components/TransactionQuestions";
import { TeamBenchmarkTab } from "../../components/TeamBenchmarkTab";
import { useCallback, useEffect, useRef, useState } from "react";
import { NavLink, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { getMe } from "../../api/auth";
import { isAxiosError } from "axios";
import { confirmTransaction, confirmTransactionFromReceipt, createAnalysisRun, editTransactionReceipt, listTransactions, moveTransactionToTrash, setFixedAsset, type TransactionApi } from "../../api/transactions";
import { listReceiptInbox, saveReceiptEdits, type ReceiptProcessingApi } from "../../api/receipts";
import { useMaskedFormat } from "../../hooks/useMaskedFormat";
import { inPeriod, isPeriod, needsReview } from "../../hooks/useReviewOverview";
import { filterLedger, matchesReviewStatus, reviewLabel, reviewStatusClass } from "../../hooks/reviewState";
import { AnalysisResult } from "../../components/AnalysisResult";
import { PeriodPicker } from "../../components/PeriodPicker";
import { PageHeader } from "../../components/PageHeader";
import { DeleteConfirmation } from "../../components/DeleteConfirmation";
import { ReceiptPreview } from "../../components/ReceiptPreview";
import { ReceiptDocumentDetails } from "../../components/ReceiptDocumentDetails";
import { SlidePanel } from "../../components/SlidePanel";
import { type SavedDocument, linesTotal } from "../../components/MonthlySalesReview";
import { apiClient } from "../../api/client";

const PREVIEW_COUNT = 5;
// 분석 대기 거래는 자동으로 분석에 포함되고, 직접 고르는 것은 애매(추가 확인 필요) 거래의 재분석뿐이다.
const isWaiting = (r: TransactionApi) => r.direction === "purchase" && matchesReviewStatus(r, "waiting");
const isSelectable = (r: TransactionApi) => r.direction === "purchase" && matchesReviewStatus(r, "caution");
export function PurchaseTransactionStoragePage({ direction = "purchase" }: { direction?: "purchase" | "sales" }) {
  const navigate = useNavigate();
  const location = useLocation();
  const fmt = useMaskedFormat();
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "all";
  const purchase = direction === "purchase";
  const combined = purchase && params.get("scope") === "all";
  const [transactions, setTransactions] = useState<TransactionApi[]>([]);
  const [inbox, setInbox] = useState<ReceiptProcessingApi[]>([]);
  const [monthly, setMonthly] = useState<SavedDocument[]>([]);
  const [simplified, setSimplified] = useState(false);
  const requestedPeriod = params.get("period");
  const validPeriod = isPeriod(requestedPeriod) ? requestedPeriod : "all";
  const period = simplified && validPeriod !== "all" ? `${validPeriod.slice(0,4)}-YEAR` : validPeriod;
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
  const [editing, setEditing] = useState(false);
  const [receiptDetail, setReceiptDetail] = useState<ReceiptProcessingApi | null>(null);
  const [receiptEditing, setReceiptEditing] = useState(false);
  // 월간 매출 정산서도 매입 거래처럼 상세 창에서 확인하고 휴지통으로 옮긴다.
  const [monthlyDetail, setMonthlyDetail] = useState<SavedDocument | null>(null);
  const [monthlyDelete, setMonthlyDelete] = useState<SavedDocument | null>(null);
  const monthlyName = (r: SavedDocument) => (r.document.사업장.상호 as string | null) || "월간 매출 정산서";
  const monthlyAmount = (r: SavedDocument) => typeof r.document.집계합계.실매출액 === "number" ? fmt.won(r.document.집계합계.실매출액) : "금액 확인 필요";
  const openDetail = (item: TransactionApi, result = false) => { setResultMode(result); setEditing(false); setFixedAssetError(""); setDetail(item); };
  const [fixedAssetBusy, setFixedAssetBusy] = useState(false);
  const [fixedAssetError, setFixedAssetError] = useState("");
  async function toggleFixedAsset(item: TransactionApi, value: boolean) {
    setFixedAssetBusy(true); setFixedAssetError("");
    try {
      const updated = await setFixedAsset(item.id, value);
      setDetail(updated);
      setTransactions(rows => rows.map(r => r.id === updated.id ? updated : r));
    } catch { setFixedAssetError("고정자산 여부를 저장하지 못했습니다. 다시 시도해 주세요."); }
    finally { setFixedAssetBusy(false); }
  }
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
  return <div className="page qa-page"><PageHeader title={combined ? "확인할 거래" : purchase ? "매입 보관함" : "매출 보관함"} showAmountToggle /><main className="page__body">
    <p className="eyebrow muted">{purchase ? "매입 증빙 및 공제 분석" : "매출 증빙 및 거래 관리"}</p><h1 className="screen-title">{combined ? "매입·매출을 함께 확인하세요" : purchase ? "내 매입 거래를 관리하세요" : "내 매출 내역을 확인하세요"}</h1>
    <nav className="vault-tabs" aria-label="보관함 종류"><NavLink to={`/storage/purchase?period=${period}`}>매입</NavLink><NavLink to={`/storage/sales?period=${period}`}>매출</NavLink><TeamBenchmarkTab /></nav>
    <PeriodPicker value={period} simplified={simplified} allowAll onChange={period=>updateFilters({period})}/>
    {combined && <p className="banner banner--info">홈 요약에서 선택한 매입·매출 거래를 함께 표시합니다.</p>}
    <div className="stat-grid stat-filters">{[["all","전체 거래",total],["review","확인 필요",review],["done",purchase ? "분석 완료" : "확정 거래",total-review]].map(([key,label,count]) => <button key={key} aria-pressed={status === key} onClick={() => filter(String(key))}><small>{label}</small><strong>{count}건</strong></button>)}</div>
    {!purchase && <section className="sales-total"><small className="muted">확정 매출 합계</small><strong>{fmt.won(periodRows.filter(r=>r.state === "confirmed").reduce((sum,r)=>sum+r.total_amount,0) + reviewedMonthly.reduce((sum,r)=>sum+linesTotal(r),0))}</strong><small className="muted">확정 거래·확인한 정산서 기준 · 공급대가 합계</small></section>}
    {message && <p className="banner banner--info" role="status">{message}</p>}
    <div className="section-heading"><h2 className="section-title">거래 목록</h2><select className="sort-select" aria-label="거래 정렬" value={order} onChange={e=>setOrder(e.target.value)}><option value="newest">최신순</option><option value="oldest">오래된순</option><option value="amount">금액순</option></select></div>
    <div className="month-filter" aria-label="거래 월"><button aria-pressed={!month} onClick={()=>{setMonth("");setSelected([]);}}>전체</button>{Array.from({length:12},(_,i)=>String(i+1)).map(m=><button key={m} aria-pressed={month===m} onClick={()=>{setMonth(m);setSelected([]);}}>{m}월</button>)}</div>
    <div className="status-tabs">{(purchase ? [["all","전체"],["waiting","분석 대기"],["caution","추가 확인 필요"],["deductible","공제"],["nondeductible","불공제"]] : [["all","전체"],["review","확인 필요"],["done","확정"]]).map(([key,label])=><button key={key} aria-pressed={status===key} onClick={()=>filter(key)}>{label}</button>)}</div>
    {loading ? <p className="center-note" role="status">거래를 불러오는 중입니다.</p> : <>
      {!filtered.length && !receipts.length && !monthlyVisible.length && <div className="empty-card"><strong>표시할 거래가 없어요</strong><p className="muted">신고 기간·월·상태를 바꾸거나 증빙을 추가해 주세요.</p></div>}
      {monthlyVisible.map(r=><article className="card ledger-card" key={`monthly-${r.id}`}><div className="ledger-head"><div><strong>{monthlyName(r)}</strong><small>{r.document.거래일 || "거래월 확인 필요"} · 월간 매출 정산서</small></div><strong>{monthlyAmount(r)}</strong></div>
      <div className="ledger-meta"><span className={`status-label ${r.status === 'reviewed' ? 'status-label--done' : 'status-label--review'}`}>{r.status === 'reviewed' ? '✓ 매출 합계 반영' : '◷ 정산서 확인 필요'}</span><button type="button" className="ledger-detail-link" onClick={()=>setMonthlyDetail(r)}>거래 상세정보 <span aria-hidden>›</span></button></div></article>)}
      {shownReceipts.map(r=><article className="card ledger-card" key={`receipt-${r.id}`}><div className="ledger-head"><div><strong>{r.vendor || "거래처 확인 필요"}</strong><small>{r.date ?? "거래일 확인 필요"}{combined && ` · ${r.direction === "sales" ? "매출" : "매입"}`}</small></div><strong>{r.amount == null ? "금액 확인 필요" : fmt.won(r.amount)}</strong></div>
      <div className="ledger-meta"><span className="status-label status-label--review">◷ 분석 대기</span><button type="button" className="ledger-detail-link" onClick={()=>{setReceiptEditing(false);setReceiptDetail(r);}}>거래 상세정보 <span aria-hidden>›</span></button></div></article>)}
      {shownRows.map(item=>{const waiting = isWaiting(item); return <article key={item.id} className="card ledger-card"><div className="ledger-head">{isSelectable(item) && <label className="ledger-selection"><input type="checkbox" aria-label={`${item.description || item.vendor} 분석 선택`} checked={visibleSelected.includes(item.id)} onChange={e=>setSelected(ids=>e.target.checked?[...ids,item.id]:ids.filter(id=>id!==item.id))}/></label>}<div><strong>{item.description || item.vendor}</strong><small>{item.transaction_date}{combined && ` · ${item.direction === "sales" ? "매출" : "매입"}`}</small></div><strong>{fmt.won(item.total_amount)}</strong></div>
      <div className="ledger-meta"><span className={`status-label ${reviewStatusClass(item)}`}>{waiting ? "◷ 분석 대기" : reviewLabel(item)}</span><button type="button" className="ledger-detail-link" disabled={busy} onClick={()=>item.state !== "confirmed" ? void openAsTransaction(()=>confirmTransaction(item.id)) : openDetail(item)}>거래 상세정보 <span aria-hidden>›</span></button></div>
      {/* 분석 결과 버튼은 매입만 둔다. 매출은 '거래 상세정보 ›'로 본다. */}
      {!waiting && item.state === "confirmed" && item.direction === "purchase" && <button className={`btn btn--sm ${needsReview(item) ? "btn--review" : "btn--result"}`} onClick={()=>openDetail(item, true)}>{needsReview(item) ? "추가 확인사항 보기" : "분석 결과 보기"}</button>}
      </article>;})}
      {hiddenCount > 0 && <button type="button" className="btn btn--secondary view-all" onClick={()=>navigate(`/storage/${direction}/receipts?${new URLSearchParams({ period, month, status, order })}`)}>전체 보기 ({receipts.length + filtered.length}건)</button>}
    </>}
    {!(purchase && judgedTab) && <div className="vault-actions">{purchase && analyzeTab && <><p className="muted">{includeWaiting ? `분석 대기 ${waitingCount}건` : `다시 분석할 거래 ${visibleSelected.length}건`}</p><button className="btn btn--primary" disabled={!(waitingCount + visibleSelected.length) || busy} onClick={()=>void analyzeAll()}>{busy?"분석 준비 중":"거래 분석하기"}</button></>}<button className="btn btn--secondary" onClick={()=>navigate(`/capture?direction=${direction}`)}>＋ {purchase?"매입":"매출"} 증빙 추가</button></div>}
    <div className="section-heading utility-row"><button className="text-link" onClick={()=>navigate(`/storage/trash?direction=${direction}`)}>휴지통</button><button className="text-link" disabled={loading} onClick={()=>void refresh()}>새로고침</button></div>
    <p className="footnote">거래 정보를 확인·확정한 후 세액 계산에 반영합니다.</p>
  </main>
  {scrolled && <button className="scroll-top" aria-label="맨 위로 이동" onClick={()=>window.scrollTo({top:0,behavior:"smooth"})}>↑</button>}
  {(deleteTarget || monthlyDelete) && <DeleteConfirmation name={monthlyDelete ? monthlyName(monthlyDelete) : deleteTarget ? deleteTarget.description || deleteTarget.vendor : ""} busy={deleting} error={deleteError} onCancel={()=>{setDeleteTarget(null);setMonthlyDelete(null);}} onConfirm={()=>void remove()} />}
  <SlidePanel open={!!monthlyDetail} label="정산서 상세" title={monthlyDetail ? monthlyName(monthlyDetail) : ""} onClose={()=>setMonthlyDetail(null)}>{monthlyDetail && <><p>{monthlyDetail.document.거래일 || "거래월 확인 필요"} · 월간 매출 정산서</p><div className="peek-amount-row"><strong className="peek-amount">{monthlyAmount(monthlyDetail)}</strong><button type="button" className="text-link" onClick={()=>navigate(`/receipts/monthly/${monthlyDetail.id}/review`)}>수정하기</button></div>
    <p className={`status-label ${monthlyDetail.status === 'reviewed' ? 'status-label--done' : 'status-label--review'}`}>{monthlyDetail.status === 'reviewed' ? '✓ 매출 합계 반영' : '◷ 정산서 확인 필요'}</p>
    <div className="field-row"><span>사업자등록번호</span><span>{monthlyDetail.document.사업장.사업자등록번호 ?? "확인 필요"}</span></div><div className="field-row"><span>세액 계산 반영 매출</span><span>{fmt.won(linesTotal(monthlyDetail))}</span></div>
    <ReceiptPreview id={monthlyDetail.id} monthly controls/>
    <button type="button" className="text-link danger" onClick={()=>{setDeleteError("");setMonthlyDelete(monthlyDetail);}}>거래 삭제</button></>}</SlidePanel>
  <SlidePanel open={!!detail} label={resultMode ? "분석 결과" : "거래 상세"} title={detail ? detail.description || detail.vendor : ""} onClose={()=>setDetail(null)}>{detail && (resultMode ? <AnalysisResult transaction={detail}/> : <><p>{detail.transaction_date} · {detail.vendor}</p><div className="peek-amount-row"><strong className="peek-amount">{fmt.won(detail.total_amount)}</strong>{detail.receipt_id && <button type="button" className="text-link" onClick={()=>setEditing(v=>!v)}>{editing ? "수정 취소" : "수정하기"}</button>}</div>
    <div className="field-row"><span>거래처</span><strong>{detail.vendor}</strong></div><div className="field-row"><span>공급가액</span><span>{detail.supply_amount==null?"확인 필요":fmt.won(detail.supply_amount)}</span></div><div className="field-row"><span>부가세</span><span>{detail.vat_amount==null?"확인 필요":fmt.won(detail.vat_amount)}</span></div>
    {detail.direction === "purchase" && <><label className="check-row"><input type="checkbox" checked={detail.is_fixed_asset} disabled={fixedAssetBusy} onChange={e=>void toggleFixedAsset(detail, e.target.checked)}/>고정자산 (1년 이상 쓰는 장비·시설)</label>
      <p className="footnote fixed-asset-note">{fixedAssetError || "세금계산서로 받으면 신고서 (12) 고정자산매입에 들어갑니다. 체크해도 공제 분석은 다시 하지 않아요."}</p></>}
    {detail.receipt_id && <><ReceiptPreview id={detail.receipt_id} controls/><ReceiptDocumentDetails receiptId={detail.receipt_id} edit={editing ? { save: (doc, details) => editTransactionReceipt(detail.id, doc, details).then(setDetail), onCancel: () => setEditing(false), onSaved: () => { setEditing(false); void refresh(); } } : undefined}/></>}
    {!editing && <>{detail.direction === "purchase" && <TransactionQuestions id={detail.id} onSaved={()=>void refresh()}/>}
    <button type="button" className="text-link danger" onClick={()=>{setDeleteError("");setDeleteTarget(detail);}}>거래 삭제</button></>}</>)}</SlidePanel>
  <SlidePanel open={!!receiptDetail} label="영수증 상세" title={receiptDetail?.vendor || "영수증"} onClose={()=>setReceiptDetail(null)}>{receiptDetail && <><p>{receiptDetail.date ?? "거래일 확인 필요"} · {receiptDetail.vendor}</p><div className="peek-amount-row"><strong className="peek-amount">{receiptDetail.amount == null ? "금액 확인 필요" : fmt.won(receiptDetail.amount)}</strong><button type="button" className="text-link" onClick={()=>setReceiptEditing(v=>!v)}>{receiptEditing ? "수정 취소" : "수정하기"}</button></div><p className="status-label status-label--review">◷ 분석 대기</p><ReceiptPreview id={receiptDetail.id} controls/><ReceiptDocumentDetails receiptId={receiptDetail.id} edit={receiptEditing ? { save: (doc, details, receipt) => saveReceiptEdits(receipt, doc, details).then(setReceiptDetail), onCancel: () => setReceiptEditing(false), onSaved: () => { setReceiptEditing(false); void refresh(); } } : undefined}/></>}</SlidePanel></div>;
}
