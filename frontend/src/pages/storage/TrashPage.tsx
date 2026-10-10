import { useCallback, useEffect, useState } from "react";
import { isAxiosError } from "axios";
import { useNavigate } from "react-router-dom";
import { listTrash, requestPermanentDelete, restoreTransaction, type TransactionApi } from "../../api/transactions";
import { PageHeader } from "../../components/PageHeader";

export function TrashPage() {
  const [items, setItems] = useState<TransactionApi[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const navigate = useNavigate();

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
    try {
      await restoreTransaction(id);
      await refresh();
      setMessage("거래를 복원했습니다. 매입 거래는 예상 세액에 다시 반영하기 전에 재분석이 필요합니다.");
    } catch {
      setMessage("거래를 복원하지 못했습니다.");
    }
  }

  async function askPermanentDelete(id: number) {
    try {
      await requestPermanentDelete(id);
      await refresh();
      setMessage("영구 삭제 요청을 기록했습니다.");
    } catch (error) {
      setMessage(isAxiosError(error) ? error.response?.data?.error?.message ?? "영구 삭제 요청을 처리하지 못했습니다." : "영구 삭제 요청을 처리하지 못했습니다.");
    }
  }

  return (
    <div className="page">
      <PageHeader title="휴지통" />
      <div className="page__body">
        <p>삭제한 거래는 예상 세액에서 제외됩니다. 복원한 매입 거래는 다시 분석해야 공제액에 반영됩니다.</p>
        {message && <div className="banner" role="status">{message}</div>}
        {loading && <div className="center-note">불러오는 중입니다.</div>}
        {!loading && items.length === 0 && <div className="center-note">휴지통이 비어 있습니다.</div>}
        {items.map((item) => (
          <article key={item.id} className="receipt-row" style={{ display: "flex", justifyContent: "space-between", gap: 12, padding: 16 }}>
            <div>
              <strong>{item.vendor}</strong>
              <div>{item.transaction_date} · {item.direction === "purchase" ? "매입" : "매출"} · {item.total_amount.toLocaleString()}원</div>
              <small>{item.description}</small>
              <div className="muted">보존 상태: {item.retention_status === "required" ? "법정 보존 기간 중" : item.retention_status === "not_required" ? "영구 삭제 요청 가능" : "보존 의무 확인 필요"}</div>
            </div>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <button className="btn btn--secondary" onClick={() => void restore(item.id)}>복원</button>
              <button className="btn btn--secondary" onClick={() => void askPermanentDelete(item.id)}>
                {item.permanent_delete_requested_at ? "요청 기록됨" : "영구 삭제 요청"}
              </button>
            </div>
          </article>
        ))}
        <button className="btn btn--secondary" style={{ marginTop: 16 }} onClick={() => navigate("/storage/purchase")}>매입 보관함으로</button>
      </div>
    </div>
  );
}
