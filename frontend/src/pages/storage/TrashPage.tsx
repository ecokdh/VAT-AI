import { useCallback, useEffect, useState } from "react";
import { isAxiosError } from "axios";
import { useNavigate, useSearchParams } from "react-router-dom";
import { apiClient } from "../../api/client";
import { deleteTransactionPermanently, listTrash, restoreTransaction, type TransactionApi } from "../../api/transactions";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { PageHeader } from "../../components/PageHeader";
import { ReceiptPreview } from "../../components/ReceiptPreview";
import { ReceiptDocumentDetails } from "../../components/ReceiptDocumentDetails";
import { SlidePanel } from "../../components/SlidePanel";
import { linesTotal, type SavedDocument } from "../../components/MonthlySalesReview";
import { useMaskedFormat } from "../../hooks/useMaskedFormat";
import { withPeriod } from "../../hooks/navigation";

// 휴지통 한 줄. 매입·매출 거래와 월간 매출 정산서를 같은 방식으로 복원하거나 영구 삭제한다.
type Entry = { key: string; name: string; date: string; kind: string; amount: number; description: string;
  restore: () => Promise<unknown>; remove: () => Promise<unknown>; transaction?: TransactionApi; monthly?: SavedDocument };
const transactionEntry = (t: TransactionApi): Entry => ({ key: `t-${t.id}`, name: t.vendor, date: t.transaction_date, kind: t.direction === "purchase" ? "매입" : "매출", amount: t.total_amount, description: t.description,
  restore: () => restoreTransaction(t.id), remove: () => deleteTransactionPermanently(t.id), transaction: t });
const monthlyEntry = (m: SavedDocument): Entry => ({ key: `m-${m.id}`, name: (m.document.사업장.상호 as string | null) || "월간 매출 정산서", date: m.document.거래일 ?? "거래월 확인 필요", kind: "월간 매출 정산서", amount: linesTotal(m), description: "",
  restore: () => apiClient.post(`/sales/monthly/${m.id}/restore`), remove: () => apiClient.delete(`/sales/monthly/${m.id}`), monthly: m });

// 휴지통: 전체 보기처럼 영수증을 나열하고, 이름으로 검색하고, 오른쪽 체크박스로 골라 복원하거나 영구 삭제한다.
export function TrashPage() {
  const fmt = useMaskedFormat();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const direction = params.get("direction") === "sales" ? "sales" : "purchase";
  const [items, setItems] = useState<Entry[]>([]);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [open, setOpen] = useState<Entry | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [rows, monthly] = await Promise.all([listTrash(), apiClient.get<SavedDocument[]>("/sales/monthly/trash").then(r => r.data)]);
      const entries = [...rows.map(transactionEntry), ...monthly.map(monthlyEntry)];
      setItems(entries); setSelected(keys => keys.filter(key => entries.some(e => e.key === key)));
    }
    catch (error) { setMessage(isAxiosError(error) ? error.response?.data?.error?.message ?? "휴지통을 불러오지 못했습니다." : "휴지통을 불러오지 못했습니다."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);

  const keyword = query.trim().toLowerCase();
  const shown = keyword ? items.filter(r => `${r.name} ${r.description}`.toLowerCase().includes(keyword)) : items;
  const shownSelected = selected.filter(key => shown.some(r => r.key === key));
  const allSelected = shown.length > 0 && shownSelected.length === shown.length;
  const toggle = (key: string, on: boolean) => setSelected(keys => on ? [...new Set([...keys, key])] : keys.filter(x => x !== key));

  // 선택한 항목마다 같은 요청을 보내고, 실패한 항목은 이름을 모아 알려 준다.
  async function applyToSelected(action: (entry: Entry) => Promise<unknown>, done: string) {
    if (busy || !shownSelected.length) return;
    setBusy(true); setMessage("");
    const failed: string[] = [];
    for (const entry of items.filter(e => shownSelected.includes(e.key))) {
      try { await action(entry); } catch { failed.push(entry.name); }
    }
    setConfirmDelete(false); setSelected([]); await refresh();
    setMessage(`${shownSelected.length - failed.length}건 ${done}${failed.length ? ` ${failed.join(", ")}은(는) 처리하지 못했습니다.` : ""}`);
    setBusy(false);
  }

  return <div className="page qa-page"><PageHeader title="휴지통" showAmountToggle onBack={() => navigate(withPeriod(`/storage/${direction}`, params.get("period")))} /><main className="page__body">
    <input className="input receipt-search" type="search" aria-label="휴지통 검색" placeholder="영수증 이름(거래처·품목)으로 검색" value={query} onChange={e => setQuery(e.target.value)} />
    <p className="muted">삭제한 거래는 예상 세액에서 제외됩니다. 복원한 매입 거래는 다시 분석해야 공제액에 반영됩니다.</p>
    {message && <p className="banner banner--info" role="status">{message}</p>}
    {loading ? <p className="center-note" role="status">불러오는 중입니다.</p> : <>
      <div className="section-heading"><p className="muted">{keyword ? `검색 결과 ${shown.length}건` : `영수증 ${items.length}건`}{shownSelected.length > 0 && ` · ${shownSelected.length}건 선택`}</p>
        {shown.length > 0 && <button type="button" className="text-link" onClick={() => setSelected(allSelected ? [] : shown.map(r => r.key))}>{allSelected ? "선택 해제" : "전체 선택"}</button>}</div>
      {!shown.length && <div className="empty-card"><strong>{keyword ? "검색 결과가 없어요" : "휴지통이 비어 있어요"}</strong></div>}
      <div className="attachment-list">{shown.map(item => <div className="attachment-row attachment-row--select" key={item.key}>
        <button type="button" className="attachment-row__main" onClick={() => setOpen(item)}>
          <span className="attachment-row__icon" aria-hidden>🧾</span>
          <span className="attachment-row__body"><strong>{item.name || "거래처 확인 필요"}</strong><small>{item.date} · {item.kind} · {fmt.won(item.amount)}{item.description && ` · ${item.description}`}</small><span className="status-label status-label--review">복원 가능</span></span>
        </button>
        <label className="attachment-check"><input type="checkbox" aria-label={`${item.name} 선택`} checked={selected.includes(item.key)} onChange={e => toggle(item.key, e.target.checked)} /></label>
      </div>)}</div>
      {items.length > 0 && <div className="btn-row trash-actions"><button className="btn btn--secondary" disabled={!shownSelected.length || busy} onClick={() => void applyToSelected(e => e.restore(), "복원했습니다. 복원한 매입 거래는 다시 분석해 주세요.")}>선택 복원</button>
        <button className="btn btn--danger" disabled={!shownSelected.length || busy} onClick={() => setConfirmDelete(true)}>선택 영구 삭제</button></div>}
    </>}
  </main>
  <ConfirmDialog open={confirmDelete} title={`${shownSelected.length}건을 영구 삭제하시겠어요?`} confirmLabel="영구 삭제" busy={busy} onCancel={() => setConfirmDelete(false)} onConfirm={() => void applyToSelected(e => e.remove(), "영구 삭제했습니다.")}>원본 사진과 함께 바로 삭제되어 복원할 수 없습니다. 필요하면 증빙을 다시 촬영해 주세요.</ConfirmDialog>
  <SlidePanel open={!!open} label="삭제한 영수증" title={open?.name || "영수증"} onClose={() => setOpen(null)}>{open && <><p>{open.date} · {fmt.won(open.amount)}</p>
    {open.monthly ? <ReceiptPreview id={open.monthly.id} monthly controls />
      : open.transaction?.receipt_id ? <><ReceiptPreview id={open.transaction.receipt_id} controls /><ReceiptDocumentDetails receiptId={open.transaction.receipt_id} /></> : <p className="muted">연결된 영수증 사진이 없습니다.</p>}</>}</SlidePanel></div>;
}
