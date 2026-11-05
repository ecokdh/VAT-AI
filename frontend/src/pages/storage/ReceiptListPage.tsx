import { useEffect, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { createAnalysisRun, listTransactions, type TransactionApi } from "../../api/transactions";
import { listReceiptInbox } from "../../api/receipts";
import { PageHeader } from "../../components/PageHeader";
import { ReceiptPreview } from "../../components/ReceiptPreview";
import { ReceiptDocumentDetails } from "../../components/ReceiptDocumentDetails";
import { SlidePanel } from "../../components/SlidePanel";
import { filterLedger, isPeriod, matchesReviewStatus, needsReview, reviewLabel, reviewStatusClass } from "../../hooks/reviewState";
import { AnalysisResult } from "../../components/AnalysisResult";
import { useMaskedFormat } from "../../hooks/useMaskedFormat";

// reanalyzeId: 추가 확인 필요(애매) 매입 거래라 다시 분석하도록 고를 수 있으면 그 거래 id.
// analyzed: 분석이 끝난 매입 거래라 보관함처럼 분석 결과를 볼 수 있으면 그 거래.
type Row = { receiptId: number; name: string; items: string; date: string | null; amount: number | null; label: string; labelClass: string; reanalyzeId?: number; analyzed?: TransactionApi };

// 보관함 '전체 보기': 보관함과 같은 기간·월·상태 조건의 영수증만 첨부파일처럼 나열하고 이름으로 검색한다.
// 추가 확인 필요 거래는 보관함처럼 골라서 다시 분석할 수 있다.
export function ReceiptListPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const direction = location.pathname.startsWith("/storage/sales") ? "sales" : "purchase";
  const [params] = useSearchParams();
  const requested = params.get("period");
  const filter = { period: isPeriod(requested) ? requested : "all", month: params.get("month") ?? "", status: params.get("status") ?? "all", order: params.get("order") ?? "newest" };
  const filterKey = JSON.stringify(filter);
  const fmt = useMaskedFormat();
  const [rows, setRows] = useState<Row[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [open, setOpen] = useState<Row | null>(null);
  const [resultMode, setResultMode] = useState(false);
  const openRow = (r: Row, result = false) => { setResultMode(result); setOpen(r); };
  const [selected, setSelected] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    Promise.all([listTransactions(direction), listReceiptInbox()]).then(([all, inbox]) => {
      if (!active) return;
      const { transactions, receipts } = filterLedger(all, inbox.filter(r => r.direction === direction), JSON.parse(filterKey));
      setRows([
        ...receipts.map(r => ({ receiptId: r.id, name: r.vendor ?? "", items: "", date: r.date, amount: r.amount, label: "분석 대기", labelClass: "status-label--review" })),
        ...transactions.filter(t => t.receipt_id != null).map(t => ({ receiptId: t.receipt_id!, name: t.vendor, items: t.description, date: t.transaction_date, amount: t.total_amount, label: reviewLabel(t), labelClass: reviewStatusClass(t), reanalyzeId: t.direction === "purchase" && matchesReviewStatus(t, "caution") ? t.id : undefined, analyzed: t.direction === "purchase" && t.state === "confirmed" && !matchesReviewStatus(t, "waiting") ? t : undefined })),
      ]);
    }).catch(() => { if (active) setError("영수증을 불러오지 못했습니다. 다시 시도해 주세요."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [direction, filterKey]);

  const keyword = query.trim().toLowerCase();
  const shown = keyword ? rows.filter(r => `${r.name} ${r.items}`.toLowerCase().includes(keyword)) : rows;
  const selectable = rows.some(r => r.reanalyzeId != null);
  const toggle = (id: number, on: boolean) => setSelected(ids => on ? [...ids, id] : ids.filter(v => v !== id));

  async function reanalyze() {
    if (busy || !selected.length) return;
    setBusy(true); setError("");
    try { const run = await createAnalysisRun(selected.slice(0, 100)); navigate(`/analysis/${run.id}`, { state: { from: location.pathname + location.search } }); }
    catch { setError("분석 작업을 시작하지 못했습니다. 잠시 후 다시 시도해 주세요."); setBusy(false); }
  }

  return <div className="page qa-page"><PageHeader title={direction === "sales" ? "매출 영수증 전체" : "매입 영수증 전체"} showAmountToggle /><main className="page__body">
    <input className="input receipt-search" type="search" aria-label="영수증 검색" placeholder="영수증 이름(거래처·품목)으로 검색" value={query} onChange={e => setQuery(e.target.value)} />
    {error && <p className="banner banner--error" role="alert">{error}</p>}
    {loading ? <p className="center-note" role="status">영수증을 불러오는 중입니다.</p> : <>
      <p className="muted">{keyword ? `검색 결과 ${shown.length}건` : `영수증 ${rows.length}건`}{filter.month && ` · ${filter.month}월`}</p>
      {!shown.length && <div className="empty-card"><strong>{keyword ? "검색 결과가 없어요" : "보관된 영수증이 없어요"}</strong></div>}
      {/* 보관함 거래 카드와 같은 형식 */}
      {shown.map(r => <article className="card ledger-card" key={r.receiptId}>
        <div className="ledger-head">{r.reanalyzeId != null && <label className="ledger-selection"><input type="checkbox" aria-label={`${r.items || r.name} 분석 선택`} checked={selected.includes(r.reanalyzeId)} onChange={e => toggle(r.reanalyzeId!, e.target.checked)} /></label>}<div><strong>{r.items || r.name || "거래처 확인 필요"}</strong><small>{r.date ?? "거래일 확인 필요"}</small></div><strong>{r.amount == null ? "금액 확인 필요" : fmt.won(r.amount)}</strong></div>
        <div className="ledger-meta"><span className={`status-label ${r.labelClass}`}>{r.label}</span><button type="button" className="ledger-detail-link" onClick={() => openRow(r)}>거래 상세정보 <span aria-hidden>›</span></button></div>
        {r.analyzed && <button type="button" className={`btn btn--sm ${needsReview(r.analyzed) ? "btn--review" : "btn--result"}`} onClick={() => openRow(r, true)}>{needsReview(r.analyzed) ? "추가 확인사항 보기" : "분석 결과 보기"}</button>}
      </article>)}
      {selectable && <div className="vault-actions"><p className="muted">다시 분석할 거래 {selected.length}건</p><button className="btn btn--primary" disabled={!selected.length || busy} onClick={() => void reanalyze()}>{busy ? "분석 준비 중" : "선택한 거래 다시 분석하기"}</button></div>}
    </>}
  </main>
  <SlidePanel open={!!open} label={resultMode ? "분석 결과" : "영수증"} title={open?.analyzed && resultMode ? open.items || open.name : open?.name || "영수증"} onClose={() => setOpen(null)}>{open && (resultMode && open.analyzed ? <AnalysisResult transaction={open.analyzed} /> : <><ReceiptPreview id={open.receiptId} controls /><ReceiptDocumentDetails receiptId={open.receiptId} /></>)}</SlidePanel></div>;
}
