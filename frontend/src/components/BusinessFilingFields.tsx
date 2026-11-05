import { validIndustryCode, type BusinessFilingInfo } from "../api/auth";

// 회원가입·마이페이지에서 함께 쓰는 신고서 기재 정보 입력칸. 모두 선택 입력이다.
export function BusinessFilingFields({ value, onChange, signup = false }: {
  value: BusinessFilingInfo; onChange: (key: keyof BusinessFilingInfo, value: string | null) => void; signup?: boolean;
}) {
  const field = (key: keyof BusinessFilingInfo, label: string, placeholder: string, extra = {}) => (
    <div className="form-field">
      <label className="form-field__label" htmlFor={`filing-${key}`}>{label}</label>
      <input id={`filing-${key}`} className="input" placeholder={placeholder} value={value[key] ?? ""} onChange={e => onChange(key, e.target.value || null)} {...extra} />
    </div>
  );
  return <section className="business-filing-fields">
    <h2 className="section-title">신고서 기재 정보</h2>
    <p className="footnote">사업자등록증에 적힌 대로 입력하면 부가세 신고서에 그대로 들어갑니다.{signup && " 나중에 마이페이지에서도 입력할 수 있어요."}</p>
    {field("business_address", "사업장 주소", "예: 서울특별시 마포구 월드컵로 12", { autoComplete: "street-address", maxLength: 255 })}
    <div className="field-grid">
      {field("business_type", "업태", "예: 음식점업", { maxLength: 100 })}
      {field("business_item", "종목", "예: 커피전문점", { maxLength: 100 })}
    </div>
    {field("industry_code", "업종코드 (6자리)", "예: 552202", { inputMode: "numeric", maxLength: 6 })}
    {!validIndustryCode(value.industry_code) && <div className="form-field__hint form-field__hint--error">업종코드는 숫자 6자리로 입력해 주세요.</div>}
  </section>;
}
