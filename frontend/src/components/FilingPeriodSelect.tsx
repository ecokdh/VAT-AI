import { Link } from "react-router-dom";
import { periodDefinitions } from "../hooks/filingPeriods";

type Props = {period:string; options:string[]; setPeriod:(value:string)=>void; profile?:{entity_type:string|null}|null; loading?:boolean; blockedReason?:string};
export function FilingPeriodSelect({period,options,setPeriod,profile,loading,blockedReason}:Props) {
  const current = periodDefinitions[period];
  const corporation = profile?.entity_type === "corporation";
  return <section className="filing-period">
    <label className="form-field"><span className="form-field__label">신고 대상 기간</span><select className="input" aria-label="신고 대상 기간" value={period} disabled={loading || !options.length} onChange={e=>setPeriod(e.target.value)}>
      {!options.length && <option value="">{loading ? "사업자정보 확인 중" : "사업자정보 입력 필요"}</option>}
      {options.map(key=><option key={key} value={key}>{periodDefinitions[key].label}{corporation && key.includes("-H") ? " 확정" : ""}</option>)}
    </select></label>
    {!loading && !options.length && <p className="banner banner--warning">{blockedReason || "사업자 형태와 과세유형을 먼저 입력해 주세요."} <Link to="/account">사업자정보 설정 ›</Link></p>}
    {current && <div className="filing-period__details"><strong>{current.kind} · 신고기한 {current.deadline.replaceAll("-", ".")}</strong><p>집계 시작일 {current.start.replaceAll("-", ".")} · {period.includes("-H") ? "반기 전체 거래 기준" : period.includes("-Q") ? "예정신고 3개월 기준" : "연간 거래 기준"}</p><details><summary>예정신고·예정고지 안내</summary><p>{corporation ? "법인은 원칙적으로 예정신고 대상이며, 직전 과세기간 공급가액 1억 5천만원 미만 소규모 법인은 예정고지 대상일 수 있습니다. 실제 대상 여부는 홈택스에서 확인하세요." : "개인 일반과세자의 예정고지는 세무서 고지액을 납부하는 절차로, 거래를 집계하는 예정신고와 구분됩니다. 간이과세자는 예정부과 및 별도 신고 대상 여부를 확인하세요."}</p><p>표시 기한은 일반적인 신고 일정입니다. 개별 연장·휴폐업·과세유형 변경은 별도 확인이 필요합니다. 기납부세액은 예상세액에서 자동 차감하지 않습니다.</p><a href="https://www.nts.go.kr/nts/cm/cntnts/cntntsView.do?cntntsId=7694&mi=2273" target="_blank" rel="noreferrer">국세청 신고납부기한 안내 ↗</a></details></div>}
  </section>;
}
