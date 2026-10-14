import { useCallback, useEffect, useRef, useState } from "react";
import { NavLink, useNavigate, useSearchParams } from "react-router-dom";
import { getMe } from "../../api/auth";
import { confirmTransaction, createAnalysisRun, listTransactions, moveTransactionToTrash, type TransactionApi } from "../../api/transactions";
import { listReceiptInbox, type ReceiptProcessingApi } from "../../api/receipts";
import { useMaskedFormat } from "../../hooks/useMaskedFormat";
import { defaultPeriod, inPeriod, isPeriod, needsReview, periodLabel, periodOptions } from "../../hooks/useReviewOverview";
import { PageHeader } from "../../components/PageHeader";
import { DeleteConfirmation } from "../../components/DeleteConfirmation";
import { ReceiptPreview } from "../../components/ReceiptPreview";

const labels: Record<string,string> = { pending:"분석 대기",not_analyzed:"분석 대기",analyzed:"공제 가능",caution:"추가 확인 필요",insufficient_info:"정보 부족",excluded:"공제 불가능",stale:"재분석 필요" };
export function PurchaseTransactionStoragePage({ direction = "purchase" }: { direction?: "purchase" | "sales" }) {
  const navigate = useNavigate();
  const fmt = useMaskedFormat();
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "all";
  const purchase = direction === "purchase";
  const [transactions, setTransactions] = useState<TransactionApi[]>([]);
  const [inbox, setInbox] = useState<ReceiptProcessingApi[]>([]);
  const [period, setPeriod] = useState(() => { const value = params.get("period"); return isPeriod(value) ? value : defaultPeriod(); });
  const [simplified, setSimplified] = useState(false);
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
  const dialog = useRef<HTMLDialogElement>(null);
  const [scrolled, setScrolled] = useState(false);
  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [rows, receipts] = await Promise.all([listTransactions(direction), listReceiptInbox()]);
      setTransactions(rows); setInbox(receipts.filter(r => r.direction === direction));
      setSelected(ids => ids.filter(id => rows.some(r => r.id === id)));
    } catch { setMessage("거래를 불러오지 못했습니다. 다시 시도해 주세요."); }
    finally { setLoading(false); }
  }, [direction]);
  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => { getMe().then(user => { if(user.business?.tax_type_code === "02") { setSimplified(true); setPeriod(current => `${current.slice(0,4)}-YEAR`); } }).catch(() => {}); }, []);
  useEffect(() => { const scroll = () => setScrolled(window.scrollY > 300); window.addEventListener("scroll", scroll); return () => window.removeEventListener("scroll", scroll); }, []);
  useEffect(() => { if(detail) dialog.current?.showModal(); }, [detail]);
  const periodRows = transactions.filter(r => inPeriod(r.transaction_date, period));
  const periodInbox = inbox.filter(r => !r.date || inPeriod(r.date, period));
  const review = periodRows.filter(needsReview).length + periodInbox.length;
  const total = periodRows.length + periodInbox.length;
  const filterStatus = (row: TransactionApi) => status === "all" || (status === "review" ? needsReview(row) : !needsReview(row));
  const filtered = periodRows.filter(r => (!month || Number(r.transaction_date.slice(5,7)) === Number(month)) && filterStatus(r)).sort((a,b) => order === "amount" ? b.total_amount-a.total_amount : order === "oldest" ? a.transaction_date.localeCompare(b.transaction_date) : b.transaction_date.localeCompare(a.transaction_date));
  const receipts = periodInbox.filter(r => status !== "done" && (!month || !r.date || Number(r.date.slice(5,7)) === Number(month)));
  const visibleSelected = selected.filter(id => filtered.some(r => r.id === id && r.state === "confirmed" && r.review_status !== "analyzed"));
  function filter(value:string) { setParams(value === "all" ? {period} : { period, status:value }, {replace:true}); setSelected([]); }
  async function analyze(ids: number[]) {
    if (!ids.length || busy) return;
    setBusy(true); setMessage("");
    try { const run = await createAnalysisRun(ids); navigate(`/analysis/${run.id}`); }
    catch { setMessage("분석 작업을 시작하지 못했습니다. 잠시 후 다시 시도해 주세요."); }
    finally { setBusy(false); }
  }
  async function remove() {
    if (!deleteTarget || deleting) return;
    setDeleting(true);
    try { await moveTransactionToTrash(deleteTarget.id); setDeleteTarget(null); await refresh(); setMessage("휴지통으로 옮겼습니다. 휴지통에서 복원할 수 있어요."); }
    catch { setDeleteError("삭제하지 못했습니다. 다시 시도해 주세요."); }
    finally { setDeleting(false); }
  }
  async function confirmDetail() {
    if (!detail || busy) return;
    setBusy(true);
    try { await confirmTransaction(detail.id); dialog.current?.close(); await refresh(); setMessage("거래를 확인·저장했습니다."); }
    catch { setMessage("거래를 확정하지 못했습니다. 거래 정보를 다시 확인해 주세요."); dialog.current?.close(); }
    finally { setBusy(false); }
  }
  let references: {title?:string; locator?:string; url?:string; source_id?:string}[] = [];
  try { const value:unknown = JSON.parse(detail?.legal_references_json ?? "[]"); if (Array.isArray(value)) references = value.filter(r => r && typeof r === "object"); } catch { /* Show missing evidence below. */ }
  return <div className="page qa-page"><PageHeader title={purchase ? "매입 보관함" : "매출 보관함"} showAmountToggle /><main className="page__body">
    <p className="eyebrow muted">{purchase ? "매입 증빙 및 공제 분석" : "매출 증빙 및 거래 관리"}</p><h1 className="screen-title">{purchase ? "내 매입 거래를 관리하세요" : "내 매출 내역을 확인하세요"}</h1>
    <nav className="vault-tabs" aria-label="보관함 종류"><NavLink to={`/storage/purchase?period=${period}`}>매입</NavLink><NavLink to={`/storage/sales?period=${period}`}>매출</NavLink></nav>
    <select className="input" aria-label="신고 기간" value={period} onChange={e => {setPeriod(e.target.value); setParams({period:e.target.value,status},{replace:true}); setSelected([]);}}>{periodOptions(simplified).map(p => <option key={p} value={p}>{periodLabel(p)} · {simplified ? "간이과세" : "일반과세 기간"}</option>)}</select>
    <div className="stat-grid stat-filters">{[["all","전체 거래",total],["review","확인 필요",review],["done",purchase ? "분석 완료" : "확정 거래",total-review]].map(([key,label,count]) => <button key={key} aria-pressed={status === key} onClick={() => filter(String(key))}><small>{label}</small><strong>{count}건</strong></button>)}</div>
    {!purchase && <section className="sales-total"><small className="muted">확정 매출 합계</small><strong>{fmt.won(periodRows.filter(r=>r.state === "confirmed").reduce((sum,r)=>sum+r.total_amount,0))}</strong><small className="muted">확정 거래 기준 · 공급대가 합계</small></section>}
    {message && <p className="banner banner--info" role="status">{message}</p>}
    <div className="section-heading"><h2 className="section-title">거래 목록</h2><select className="sort-select" aria-label="거래 정렬" value={order} onChange={e=>setOrder(e.target.value)}><option value="newest">최신순</option><option value="oldest">오래된순</option><option value="amount">금액순</option></select></div>
    <div className="month-filter" aria-label="거래 월"><button aria-pressed={!month} onClick={()=>{setMonth("");setSelected([]);}}>전체</button>{Array.from({length:12},(_,i)=>String(i+1)).map(m=><button key={m} aria-pressed={month===m} onClick={()=>{setMonth(m);setSelected([]);}}>{m}월</button>)}</div>
    <div className="status-tabs">{[["all","전체"],["review","확인 필요"],["done",purchase?"분석 완료":"확정"]].map(([key,label])=><button key={key} aria-pressed={status===key} onClick={()=>filter(key)}>{label}</button>)}</div>
    {loading ? <p className="center-note" role="status">거래를 불러오는 중입니다.</p> : <>
      {!filtered.length && !receipts.length && <div className="empty-card"><strong>표시할 거래가 없어요</strong><p className="muted">신고 기간·월·상태를 바꾸거나 증빙을 추가해 주세요.</p></div>}
      {receipts.map(r=><article className="card ledger-card" key={`receipt-${r.id}`}><div className="ledger-head"><div><strong>{r.vendor || "거래처 확인 필요"}</strong><small>{r.date ?? "거래일 확인 필요"}</small></div><strong>{r.amount == null ? "금액 확인 필요" : fmt.won(r.amount)}</strong></div><p className="status-label status-label--review">◷ 거래 확인 필요</p><button className="btn btn--primary btn--sm" onClick={()=>navigate(`/receipts/${r.id}/edit`)}>거래 정보 확인·저장</button></article>)}
      {filtered.map(item=><article key={item.id} className="card ledger-card"><div className="ledger-head">{purchase && <input type="checkbox" aria-label={`${item.description || item.vendor} 분석 선택`} checked={visibleSelected.includes(item.id)} disabled={item.state!=="confirmed" || item.review_status==="analyzed"} onChange={e=>setSelected(ids=>e.target.checked?[...ids,item.id]:ids.filter(id=>id!==item.id))}/>}<div><strong>{item.description || item.vendor}</strong><small>{item.transaction_date}</small></div><strong>{fmt.won(item.total_amount)}</strong></div>
      <div className={`status-label ${needsReview(item) ? "status-label--review" : "status-label--done"}`}>{purchase ? labels[item.review_status] ?? "확인 필요" : item.state==="confirmed" ? "✓ 확정" : "◷ 확인 필요"}</div>
      <details className="ledger-details"><summary>거래 상세정보</summary><div className="field-row"><span>거래처</span><strong>{item.vendor}</strong></div><div className="field-row"><span>공급가액</span><span>{item.supply_amount==null?"확인 필요":fmt.won(item.supply_amount)}</span></div><div className="field-row"><span>부가세</span><span>{item.vat_amount==null?"확인 필요":fmt.won(item.vat_amount)}</span></div><button className="text-link danger" onClick={()=>{setDeleteError("");setDeleteTarget(item);}}>거래 삭제</button></details>
      {item.state !== "confirmed" ? <button className="btn btn--primary btn--sm" onClick={()=>setDetail(item)}>거래 정보 확인·저장</button> : purchase && ["not_analyzed","pending","stale"].includes(item.review_status) ? <button className="btn btn--ghost btn--sm" disabled={busy} onClick={()=>void analyze([item.id])}>공제 분석하기</button> : <button className="btn btn--ghost btn--sm" onClick={()=>setDetail(item)}>{purchase ? needsReview(item) ? "추가 확인사항 보기" : "분석 결과 보기" : "거래 상세 보기"}</button>}
      </article>)}
    </>}
    <div className="vault-actions">{purchase && <><p className="muted">선택한 거래: {visibleSelected.length}건</p><button className="btn btn--primary" disabled={!visibleSelected.length || busy} onClick={()=>void analyze(visibleSelected)}>{busy?"분석 준비 중":"선택 거래 분석하기"}</button></>}<button className="btn btn--secondary" onClick={()=>navigate(`/capture?direction=${direction}`)}>＋ {purchase?"매입":"매출"} 증빙 추가</button></div>
    <div className="section-heading utility-row"><button className="text-link" onClick={()=>navigate(`/storage/trash?direction=${direction}`)}>휴지통</button><button className="text-link" disabled={loading} onClick={()=>void refresh()}>새로고침</button></div>
    <p className="footnote">거래 정보를 확인·확정한 후 세액 계산에 반영합니다.</p>
  </main>
  {scrolled && <button className="scroll-top" aria-label="맨 위로 이동" onClick={()=>window.scrollTo({top:0,behavior:"smooth"})}>↑</button>}
  {deleteTarget && <DeleteConfirmation name={deleteTarget.description || deleteTarget.vendor} busy={deleting} error={deleteError} onCancel={()=>setDeleteTarget(null)} onConfirm={()=>void remove()} />}
  <dialog ref={dialog} className="analysis-peek" aria-label="거래 상세" onClose={()=>setDetail(null)}>{detail && <><div className="section-heading"><h2>{detail.description || detail.vendor}</h2><button className="icon-btn" aria-label="상세 닫기" onClick={()=>dialog.current?.close()}>×</button></div><p>{detail.transaction_date} · {detail.vendor}</p><strong>{fmt.won(detail.total_amount)}</strong>{detail.receipt_id && <ReceiptPreview id={detail.receipt_id}/>}
  {detail.state !== "confirmed" && <button className="btn btn--primary" disabled={busy} onClick={()=>void confirmDetail()}>확인한 거래 확정하기</button>}{purchase && <><h3>{labels[detail.review_status] ?? "확인 필요"}</h3><p>{detail.analysis_reason ?? "아직 연결된 분석 결과가 없습니다."}</p><h3>판례·세법 근거</h3>{references.length ? references.map((ref,i)=><article className="card" key={i}><strong>{ref.title || ref.source_id}</strong><p>{ref.locator}</p>{typeof ref.url==="string" && /^https?:\/\//i.test(ref.url) && <a className="text-link" href={ref.url} target="_blank" rel="noreferrer">근거 원문 열기 ↗</a>}</article>) : <p className="muted">연결된 근거 자료가 없습니다. 근거를 확인한 뒤 판단해 주세요.</p>}</>}
  </>}</dialog></div>;
}
