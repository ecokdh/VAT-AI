import { useCallback, useEffect, useState } from "react";
import { isAxiosError } from "axios";
import { useNavigate, useSearchParams } from "react-router-dom";
import { listTrash, requestPermanentDelete, restoreTransaction, type TransactionApi } from "../../api/transactions";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { useMaskedFormat } from "../../hooks/useMaskedFormat";
import { PageHeader } from "../../components/PageHeader";

export function TrashPage() {
  const fmt=useMaskedFormat();
  const [deleteTarget,setDeleteTarget]=useState<TransactionApi|null>(null);
  const [deleting,setDeleting]=useState(false);
  const [items, setItems] = useState<TransactionApi[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const direction = params.get("direction") === "sales" ? "sales" : "purchase";
  const vaultLabel = direction === "sales" ? "매출" : "매입";
  const [restoring, setRestoring] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setMessage("");
    try {
      setItems(await listTrash());
    } catch (error) {
      setMessage(isAxiosError(error) ? error.response?.data?.error?.message ?? "휴지통을 불러오지 못했습니다." : "휴지통을 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  async function restore(id: number) {
    if (restoring) return;
    setRestoring(true);
    try {
      const restored = await restoreTransaction(id);
      setParams({ direction: restored.direction }, { replace: true });
      await refresh();
      setMessage(restored.direction === "sales" ? "매출 거래를 복원했습니다. 매출 보관함에서 확인할 수 있어요." : "매입 거래를 복원했습니다. 예상 세액에 다시 반영하기 전에 재분석이 필요합니다.");
    } catch {
      setMessage("거래를 복원하지 못했습니다.");
    } finally {
      setRestoring(false);
    }
  }

  async function askPermanentDelete(id: number) {
    if(deleting)return; setDeleting(true);
    try {
      await requestPermanentDelete(id);
      await refresh();
      setDeleteTarget(null);
      setMessage("영구 삭제 요청을 기록했습니다. 보존 상태 확인 후 처리됩니다.");
    } catch (error) {
      setMessage(isAxiosError(error) ? error.response?.data?.error?.message ?? "영구 삭제 요청을 처리하지 못했습니다." : "영구 삭제 요청을 처리하지 못했습니다.");
    } finally { setDeleting(false); }
  }

  return (
    <div className="page qa-page">
      <PageHeader title="휴지통" onBack={() => navigate(`/storage/${direction}`)} />
      <div className="page__body">
        <p>삭제한 거래는 예상 세액에서 제외됩니다. 복원한 매입 거래는 다시 분석해야 공제액에 반영됩니다.</p>
        {message && <div className="banner" role="status">{message}</div>}
        {loading && <div className="center-note">불러오는 중입니다.</div>}
        {!loading && items.length === 0 && <div className="center-note">휴지통이 비어 있습니다.</div>}
        {items.map((item) => (
          <article key={item.id} className="card trash-card">
            <div>
              <strong>{item.vendor}</strong>
              <div>{item.transaction_date} · {item.direction === "purchase" ? "매입" : "매출"} · {fmt.won(item.total_amount)}</div>
              <small>{item.description}</small>
              <div className="muted">보존 상태: {item.retention_status === "required" ? "법정 보존 기간 중" : item.retention_status === "not_required" ? "영구 삭제 요청 가능" : "보존 의무 확인 필요"}</div>
            </div>
            <div className="btn-row trash-actions">
              <button className="btn btn--secondary" disabled={restoring} onClick={() => void restore(item.id)}>복원</button>
              <button className="btn btn--danger-outline" disabled={!!item.permanent_delete_requested_at || deleting} onClick={() => setDeleteTarget(item)}>
                {item.permanent_delete_requested_at ? "삭제 요청 접수됨" : "영구 삭제"}
              </button>
            </div>
          </article>
        ))}
        <ConfirmDialog open={!!deleteTarget} title="영구 삭제를 요청하시겠어요?" confirmLabel="영구 삭제" busy={deleting} onCancel={()=>setDeleteTarget(null)} onConfirm={()=>{if(deleteTarget)void askPermanentDelete(deleteTarget.id);}}>보존 의무가 없는 거래만 요청할 수 있습니다. 요청은 기록되며, 실제 삭제가 완료되면 복원할 수 없습니다.</ConfirmDialog>
        <button className="btn btn--secondary" style={{ marginTop: 16 }} onClick={() => navigate(`/storage/${direction}`)}>{vaultLabel} 보관함으로 이동</button>
      </div>
    </div>
  );
}
