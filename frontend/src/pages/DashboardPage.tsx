import { useNavigate } from "react-router-dom";
import { useMaskedFormat } from "../hooks/useMaskedFormat";
import { useReviewOverview, periodLabel, periodOptions } from "../hooks/useReviewOverview";
import { AmountVisibilityToggle } from "../components/AmountVisibilityToggle";
import { AccountMenu } from "../components/AccountMenu";
import { ProfileAvatar } from "../components/ProfileAvatar";

export function DashboardPage() {
  const navigate = useNavigate();
  const fmt = useMaskedFormat();
  const view = useReviewOverview();
  const need = view.unconfirmed + view.pending;
  const go = (path: string) => navigate(`${path}${path.includes("?") ? "&" : "?"}period=${view.period}`);
  return <div className="page qa-page"><header className="page-header"><AccountMenu /><strong>VAT-AI</strong><button className="icon-btn" aria-label="마이페이지" onClick={() => navigate("/account")}><ProfileAvatar userId={view.user?.id} /></button></header>
    <main className="page__body">
      <p className="muted eyebrow">{view.user?.business?.business_name ?? view.user?.name ?? "내 사업장"}</p>
      <h1 className="screen-title">신고 준비 현황을 확인하세요</h1><p className="muted">확인이 필요한 거래부터 차근차근 정리해요.</p>
      {view.error && <p className="banner banner--error" role="alert">{view.error}</p>}
      <label className="form-field"><span className="form-field__label">신고 대상 기간</span><select className="input" value={view.period} onChange={e => view.setPeriod(e.target.value)}>{periodOptions(view.user?.business?.tax_type_code === "02").map(p => <option key={p} value={p}>{periodLabel(p)}</option>)}</select></label>
      <section className="summary-card summary-card--primary review-hero">
        <div className="section-heading"><span>예상 납부세액</span><AmountVisibilityToggle /></div>
        <strong className="hero-amount">{view.loading ? "불러오는 중" : view.estimate?.payable_estimate == null ? "확인 필요" : fmt.won(view.estimate.payable_estimate)}</strong>
        <p className="hero-caption">{view.estimate ? "확정 거래 기준 · 참고용 추정치" : "사업자 과세유형을 확인하면 예상 세액을 볼 수 있어요."}</p>
        <div className="readiness"><div className="section-heading"><span>신고 준비 상태</span><strong>확인 필요 {need}건</strong></div><div className="readiness-track" role="progressbar" aria-label="확인이 필요한 거래 비율" aria-valuemin={0} aria-valuemax={100} aria-valuenow={view.total ? Math.round(need / view.total * 100) : 0}><span style={{ width: `${view.total ? need / view.total * 100 : 0}%` }} /></div><p>{view.loading ? "거래를 확인하고 있어요" : view.total ? `${view.total}건 중 ${need}건이 확인 필요해요` : "증빙을 등록해 신고 준비를 시작해 보세요"}</p></div>
      </section>
      <h2 className="section-title">지금 확인할 항목</h2><section className="card action-list">
        <button onClick={() => go(`/storage/${view.firstDirection}?status=review`)}><span><strong>거래 정보 확인 {view.unconfirmed}건</strong><small>매입·매출 보관함에서 확인하고 저장해요</small></span><span>›</span></button>
        <button onClick={() => go("/storage/purchase?status=review")}><span><strong>공제 분석 확인 {view.pending}건</strong><small>분석 대기와 추가 확인이 필요한 거래예요</small></span><span>›</span></button>
      </section>
      <section className="card overview-card"><div className="section-heading"><h2 className="section-title">신고 준비 요약</h2><button className="text-link" onClick={() => go("/reports")}>자세히 ›</button></div><div className="stat-grid">{[["전체 거래",view.total],["준비 완료",view.ready],["확인 필요",need]].map(([label,count]) => <div key={label}><strong>{count}</strong><small>{label}</small></div>)}</div></section>
      <button className="btn btn--primary" onClick={() => go("/reports")}>신고 전 검토하기 →</button><p className="footnote">VAT-AI는 신고를 지원하며 홈택스에 직접 제출하지 않습니다.</p>
    </main></div>;
}
