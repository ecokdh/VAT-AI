import { useNavigate } from "react-router-dom";
import { useMaskedFormat } from "../hooks/useMaskedFormat";
import { useReviewOverview } from "../hooks/useReviewOverview";
import { PeriodPicker } from "../components/PeriodPicker";
import { AmountVisibilityToggle } from "../components/AmountVisibilityToggle";
import { AccountMenu } from "../components/AccountMenu";
import { ProfilePhoto } from "../components/ProfileAvatar";
import { BrandWordmark } from "../components/BrandMark";
import { Icon } from "../components/Icon";
import "../styles/dashboard.css";

export function DashboardPage() {
 const navigate=useNavigate(); const fmt=useMaskedFormat(); const view=useReviewOverview();
 const need=view.unconfirmed+view.pending;
 const estimate=view.estimate;
 const credit=estimate?.eligible_input_vat==null||estimate.deemed_input_vat==null?null:estimate.eligible_input_vat+estimate.deemed_input_vat;
 const go=(path:string)=>navigate(`${path}${path.includes("?")?"&":"?"}period=${view.period}`);
 return <div className="page qa-page dashboard-page"><header className="page-header"><AccountMenu/><strong className="brand-title"><BrandWordmark/><span className="sr-only">VAT-AI</span></strong><div className="dashboard-header__actions"><AmountVisibilityToggle/><ProfilePhoto userId={view.user?.id} showAccount/></div></header>
  <main className="page__body">
   <p className="business-name"><span className="business-name__icon"><Icon name="store" size={16}/></span>{view.user?.business?.business_name??"내 사업장"}</p>
   {view.error&&<p className="banner banner--error" role="alert">{view.error}</p>}
   <PeriodPicker value={view.period} simplified={view.user?.business?.tax_type_code==="02"} onChange={period=>view.setPeriod(period)}/>
   <section className="summary-card summary-card--primary review-hero">
    <div className="section-heading"><span>예상 공제세액</span></div>
    <strong className="hero-amount">{view.loading?"불러오는 중":credit==null?"확인 필요":fmt.won(credit)}</strong>
    <p className="hero-caption">확정 거래·공제 분석 기준 · 참고용 추정치</p>
    <div className="hero-secondary"><span>예상 납부세액</span><strong>{estimate?.payable_estimate==null?"확인 필요":fmt.won(estimate.payable_estimate)}</strong></div>
    <div className="readiness"><div className="section-heading"><span>신고 준비 상태</span><strong>확인 필요 {need}건</strong></div><div className="readiness-track" role="progressbar" aria-label="신고 준비 완료 비율" aria-valuemin={0} aria-valuemax={100} aria-valuenow={view.total?Math.round((view.total-need)/view.total*100):0}><span style={{width:`${view.total?(view.total-need)/view.total*100:0}%`}}/></div><p>{view.total?`${view.total}건 중 ${need}건이 확인 필요해요`:"증빙을 등록해 신고 준비를 시작해 보세요"}</p></div>
   </section>
   {view.period.startsWith("2025-")&&<p className="banner banner--info">2025년 거래 조회입니다. 현재 세액 계산은 2026년 규칙만 지원합니다.</p>}
   <section className="card overview-card"><div className="section-heading"><h2 className="section-title">신고 준비 요약</h2><span className="muted">전체 거래 {view.total}건</span></div>
    <div className="stat-grid summary-filters">{[["공제",view.readiness?.deductible??0,"deductible"],["불공제",view.readiness?.nondeductible??0,"nondeductible"],["확인 필요",need,"review"]].map(([label,count,status])=><button key={label} disabled={view.loading} aria-label={`${label} ${count}건 보기`} onClick={()=>go(`/storage/purchase?status=${status}${status==="review"?"&scope=all":""}`)}><strong>{count}</strong><small>{label} <span aria-hidden="true">›</span></small></button>)}</div>
    {!view.loading&&view.total===0&&<p className="muted">선택한 기간에 등록된 거래가 없습니다.</p>}
   </section>
   <button className="btn btn--primary" onClick={()=>go("/reports")}>신고서 생성 →</button><p className="footnote">VAT-AI는 신고를 지원하며 홈택스에 직접 제출하지 않습니다.</p>
  </main></div>;
}
