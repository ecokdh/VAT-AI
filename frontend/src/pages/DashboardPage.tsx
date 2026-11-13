import { Link, useNavigate } from "react-router-dom";
import { useReviewOverview } from "../hooks/useReviewOverview";
import { PeriodPicker } from "../components/PeriodPicker";
import { ProfileAvatar } from "../components/ProfileAvatar";
import { BrandMark } from "../components/BrandMark";
import { Icon } from "../components/Icon";
import { formatWon } from "../utils/format";
import "../styles/dashboard.css";

// 신고 준비 요약 타일 아이콘: 공제 ✓ · 불공제 ✕ · 확인 필요 !
const STATUS_ICON = { check: "M6 12.5l4 4 8-9", x: "M7 7l10 10M17 7L7 17", alert: "M12 6.5v7M12 17.5v.01" };

export function DashboardPage() {
 const navigate=useNavigate();const view=useReviewOverview();
 const need=view.unconfirmed+view.pending;
 const estimate=view.estimate;
 const credit=estimate?.eligible_input_vat==null||estimate.deemed_input_vat==null?null:estimate.eligible_input_vat+estimate.deemed_input_vat;
 const go=(path:string)=>navigate(`${path}${path.includes("?")?"&":"?"}period=${view.period}`);
 const ready=view.total?(view.total-need)/view.total*100:0;
 const stats=[["공제",view.readiness?.deductible??0,"deductible","check"],["불공제",view.readiness?.nondeductible??0,"nondeductible","x"],["확인 필요",need,"review","alert"]] as const;
 return <div className="page qa-page dashboard-page"><header className="page-header"><span aria-hidden="true" /><span className="dash-logo"><BrandMark/><span className="sr-only">VAT-AI</span></span><Link className="profile-photo-trigger" to="/account" aria-label="마이페이지"><ProfileAvatar userId={view.user?.id}/></Link></header>
  <main className="page__body">
   <div className="dash-top">
    <p className="business-name"><Icon name="store" size={20}/>{view.user?.business?.business_name??"내 사업장"}</p>
    <PeriodPicker value={view.period} simplified={view.user?.business?.tax_type_code==="02"} onChange={period=>view.setPeriod(period)}/>
   </div>
   {view.error&&<p className="banner banner--error" role="alert">{view.error}</p>}
   <section className="dash-hero">
    <span className="dash-hero__label">예상 공제세액</span>
    <strong className="dash-hero__amount">{view.loading?"불러오는 중":credit==null?"확인 필요":formatWon(credit)}</strong>
    <span className="dash-hero__caption">확정 거래·공제 분석 기준 · 참고용 추정치</span>
    <div className="dash-hero__row"><span>예상 납부세액</span><strong>{view.loading?"불러오는 중":view.salesPending?"매출 확인 필요":estimate?.payable_estimate==null?"확인 필요":formatWon(estimate.payable_estimate)}</strong></div>
    <div className="dash-hero__row dash-hero__row--plain"><span>신고 준비 상태</span><span>확인 필요 {need}건</span></div>
    <div className="dash-hero__track" role="progressbar" aria-label="신고 준비 완료 비율" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(ready)}><span style={{width:`${ready}%`}}/></div>
    <span className="dash-hero__caption">{view.total?`${view.total}건 중 ${need}건이 확인 필요해요`:"증빙을 등록해 신고 준비를 시작해 보세요"}</span>
   </section>
   <section className="dash-summary"><div className="dash-summary__head"><h2>신고 준비 요약</h2><span>전체 거래 {view.total}건</span></div>
    <div className="dash-tiles">{stats.map(([label,count,status,icon])=><button key={label} className={`dash-tile dash-tile--${status}`} disabled={view.loading} aria-label={`${label} ${count}건 보기`} onClick={()=>go(`/storage/purchase?status=${status}${status==="review"?"&scope=all":""}`)}><span className="dash-tile__icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d={STATUS_ICON[icon]}/></svg></span><strong>{count}</strong><small>{label}<span aria-hidden="true">›</span></small></button>)}</div>
    {!view.loading&&view.total===0&&<p className="dash-empty">선택한 기간에 등록된 거래가 없습니다.</p>}
   </section>
   <button className="btn btn--primary dash-cta" onClick={()=>go("/reports")}>신고서 생성</button><p className="footnote">VAT-AI는 신고를 지원하며 홈택스에 직접 제출하지 않습니다.</p>
  </main></div>;
}
