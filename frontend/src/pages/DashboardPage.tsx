import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMaskedFormat } from "../hooks/useMaskedFormat";
import { AmountVisibilityToggle } from "../components/AmountVisibilityToggle";
import { AccountMenu } from "../components/AccountMenu";
import { Icon } from "../components/Icon";
import { getMe, type AuthUser } from "../api/auth";
import { getTaxEstimate, listTransactions, type TaxEstimateApi, type TransactionApi } from "../api/transactions";

export function DashboardPage() {
  const navigate = useNavigate();
  const fmt = useMaskedFormat();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [purchases, setPurchases] = useState<TransactionApi[]>([]);
  const [sales, setSales] = useState<TransactionApi[]>([]);
  const [estimate, setEstimate] = useState<TaxEstimateApi | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const [account, purchaseRows, salesRows] = await Promise.all([getMe(), listTransactions("purchase"), listTransactions("sales")]);
        if (!active) return;
        setUser(account); setPurchases(purchaseRows); setSales(salesRows);
        const period = account.business?.tax_type_code === "02" ? "2026-YEAR" : new Date().getMonth() < 6 ? "2026-H1" : "2026-H2";
        if (["01", "02"].includes(account.business?.tax_type_code ?? "")) {
          const result = await getTaxEstimate(period);
          if (active) setEstimate(result);
        }
      } catch { if (active) setError("정보를 불러오지 못했습니다. 로그인 상태와 서버 연결을 확인해 주세요."); }
      finally { if (active) setLoading(false); }
    }
    void load();
    return () => { active = false; };
  }, []);
  const stale = purchases.filter((row) => row.review_status === "stale").length;
  return <div className="page"><header className="page-header"><AccountMenu /><strong>VAT-AI</strong><AmountVisibilityToggle /></header>
    <div className="page__body">
      <p className="muted">{user?.business?.business_name ?? "내 사업장"}</p>
      <h1 className="screen-title">{user?.name ?? "사용자"}님,<br />오늘의 거래를 정리해 볼까요?</h1>
      {error && <p className="banner banner--error" role="alert">{error}</p>}
      <section className="summary-card summary-card--primary">
        <div className="summary-card__eyebrow">{estimate?.period ?? "현재 신고 기간"} 예상 납부세액</div>
        <div style={{ fontSize: 32, fontWeight: 800, margin: "12px 0" }}>{loading ? "불러오는 중" : estimate?.payable_estimate == null ? "확인 필요" : fmt.won(estimate.payable_estimate)}</div>
        <p style={{ fontSize: 13, margin: 0 }}>{estimate ? "확인된 거래 기준의 예상 금액입니다." : "사업자 정보와 거래를 확인하면 예상 세액을 볼 수 있어요."}</p>
      </section>
      {stale > 0 && <button className="banner banner--warning" style={{ width: "100%", marginTop: 16 }} onClick={() => navigate("/storage/purchase")}>다시 분석할 거래 {stale}건을 확인해 주세요 ›</button>}
      <button className="card capture-choice" style={{ width: "100%", marginTop: 20 }} onClick={() => navigate("/capture")}><Icon name="camera" size={30} /><span><strong>계산서 촬영 (OCR)</strong><small>매입·매출 선택 후 증빙 등록</small></span><span>›</span></button>
      <h2 style={{ fontSize: 18, marginTop: 28 }}>내 보관함</h2>
      <div className="vault-grid">{([['purchase', '매입', purchases], ['sales', '매출', sales]] as const).map(([direction, label, rows]) => <button key={direction} className="card vault-card" onClick={() => navigate(`/storage/${direction}`)}><Icon name="folder" /><strong>{label} 보관함</strong><span className="muted">{rows.length}건</span><strong>{fmt.won(rows.reduce((sum, row) => sum + row.total_amount, 0))}</strong></button>)}</div>
      <button className="btn btn--secondary" style={{ marginTop: 20 }} onClick={() => navigate("/reports")}>신고 전 검토 · 리포트</button>
    </div>
  </div>;
}
