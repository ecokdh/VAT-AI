import { useEffect, useState } from "react";
import { isAxiosError } from "axios";
import { getMe } from "../api/auth";
import { getTaxProfile, saveTaxProfile, type TaxProfileApi, type TaxProfileInput } from "../api/transactions";
export function TaxProfileForm() {
  const [taxProfile, setTaxProfile] = useState<TaxProfileApi | null>(null);
  const [taxType, setTaxType] = useState<string | null>(null);
  const [profileSaving, setProfileSaving] = useState(false);
  const [message, setMessage] = useState("");
  useEffect(() => { Promise.all([getTaxProfile(), getMe()]).then(([profile,user]) => { setTaxProfile(profile); setTaxType(user.business?.tax_type_code === "02" ? "simplified" : user.business?.tax_type_code === "01" ? "general" : null); }).catch(() => setMessage("사업자 설정을 불러오지 못했습니다.")); }, []);
  async function saveProfile(confirmed: boolean) {
    if (!taxProfile) return;
    setProfileSaving(true);
    setMessage("");
    try {
      const input: TaxProfileInput = { ...taxProfile, confirmed };
      setTaxProfile(await saveTaxProfile(input));
      setMessage(confirmed ? "사업자·과세기간 정보를 확인했습니다." : "사업자 정보를 저장했습니다. 확인 전에는 세율·공제 한도 판단에 사용하지 않습니다.");
    } catch (error) {
      setMessage(isAxiosError(error) ? error.response?.data?.error?.message ?? "사업자 정보를 저장하지 못했습니다." : "사업자 정보를 저장하지 못했습니다.");
    } finally {
      setProfileSaving(false);
    }
  }

  function updateProfile<K extends keyof TaxProfileApi>(key: K, value: TaxProfileApi[K]) {
    setTaxProfile((current) => current ? { ...current, [key]: value, confirmed: false } : current);
  }


return <>{message && <p className="banner banner--info" role="status">{message}</p>}{taxProfile &&           <details className="card" style={{ marginBottom: 16 }}>
            <summary style={{ cursor: "pointer", fontWeight: 600 }}>2026 사업자·과세기간 정보 {taxProfile.confirmed ? "(확인 완료)" : "(확인 필요)"}</summary>
            <p className="muted">입력한 값은 확인 완료 후 계산에 사용됩니다. 불명확한 거래는 자동으로 추정하지 않습니다.</p>
            <div className="form-field"><label className="form-field__label" htmlFor="entity-type">사업자 형태</label><select id="entity-type" className="input" value={taxProfile.entity_type ?? ""} onChange={(e) => updateProfile("entity_type", (e.target.value || null) as TaxProfileApi["entity_type"])}><option value="">선택</option><option value="individual">개인</option><option value="corporation">법인</option></select></div>
            <div className="form-field"><label className="form-field__label" htmlFor="industry-category">업종</label><select id="industry-category" className="input" value={taxProfile.industry_category ?? ""} onChange={(e) => updateProfile("industry_category", (e.target.value || null) as TaxProfileApi["industry_category"])}><option value="">선택</option><option value="food_service">음식점업</option><option value="manufacturing">제조업</option><option value="other">그 외 업종</option></select></div>
            {taxProfile.industry_category !== "other" && <div className="form-field"><label className="form-field__label" htmlFor="industry-subtype">세부 업종</label><select id="industry-subtype" className="input" value={taxProfile.industry_subtype ?? ""} onChange={(e) => updateProfile("industry_subtype", (e.target.value || null) as TaxProfileApi["industry_subtype"])}><option value="">선택</option>{taxProfile.industry_category === "food_service" ? <><option value="restaurant">일반 음식점</option><option value="taxable_entertainment">과세 유흥장소</option></> : <><option value="specified_mill">특정 제분업</option><option value="other">그 외 제조업</option></>}</select></div>}
            {taxProfile.industry_category === "manufacturing" && taxProfile.entity_type === "corporation" && <div className="form-field"><label className="form-field__label" htmlFor="sme-status">중소기업 여부</label><select id="sme-status" className="input" value={taxProfile.is_sme == null ? "" : String(taxProfile.is_sme)} onChange={(e) => updateProfile("is_sme", e.target.value === "" ? null : e.target.value === "true")}><option value="">확인 필요</option><option value="true">중소기업</option><option value="false">중소기업 아님</option></select></div>}
            <div className="field-row"><label htmlFor="sales-h1">2026년 1기 과세 매출액</label><input id="sales-h1" className="input" inputMode="numeric" value={taxProfile.taxable_sales_h1 ?? ""} onChange={(e) => updateProfile("taxable_sales_h1", e.target.value === "" ? null : Number(e.target.value.replace(/[^0-9]/g, "")))} /></div>
            <div className="field-row"><label htmlFor="sales-h2">2026년 2기 과세 매출액</label><input id="sales-h2" className="input" inputMode="numeric" value={taxProfile.taxable_sales_h2 ?? ""} onChange={(e) => updateProfile("taxable_sales_h2", e.target.value === "" ? null : Number(e.target.value.replace(/[^0-9]/g, "")))} /></div>
            {taxType === "general" && <>
              <p className="muted">의제매입 공제 한도에 쓰는 관련 매출액은 전체 과세 매출액과 다를 수 있습니다. 면세 원재료를 사용해 과세 공급한 금액을 확인해 입력하세요.</p>
              <div className="field-row"><label htmlFor="deemed-sales-h1">1기 의제매입 관련 과세 매출액</label><input id="deemed-sales-h1" className="input" inputMode="numeric" value={taxProfile.deemed_related_taxable_sales_h1 ?? ""} onChange={(e) => updateProfile("deemed_related_taxable_sales_h1", e.target.value === "" ? null : Number(e.target.value.replace(/[^0-9]/g, "")))} /></div>
              <div className="field-row"><label htmlFor="deemed-sales-h2">2기 의제매입 관련 과세 매출액</label><input id="deemed-sales-h2" className="input" inputMode="numeric" value={taxProfile.deemed_related_taxable_sales_h2 ?? ""} onChange={(e) => updateProfile("deemed_related_taxable_sales_h2", e.target.value === "" ? null : Number(e.target.value.replace(/[^0-9]/g, "")))} /></div>
            </>}
            {taxType === "simplified" && <div className="form-field"><label className="form-field__label" htmlFor="simplified-rate">간이과세 업종별 부가가치율 (국세청 확인값)</label><select id="simplified-rate" className="input" value={taxProfile.simplified_industry_rate ?? ""} onChange={(e) => updateProfile("simplified_industry_rate", e.target.value === "" ? null : Number(e.target.value))}><option value="">확인 필요</option>{[15, 20, 25, 30, 40].map((rate) => <option key={rate} value={rate}>{rate}%</option>)}</select></div>}
            <div className="field-row"><label htmlFor="business-start">개업일</label><input id="business-start" className="input" type="date" value={taxProfile.business_start_date ?? ""} onChange={(e) => updateProfile("business_start_date", e.target.value || null)} /></div>
            <div className="field-row"><label htmlFor="business-end">폐업일 (해당 시)</label><input id="business-end" className="input" type="date" value={taxProfile.business_end_date ?? ""} onChange={(e) => updateProfile("business_end_date", e.target.value || null)} /></div>
            <div className="field-row"><label htmlFor="tax-change-date">과세유형 변경일 (해당 시)</label><input id="tax-change-date" className="input" type="date" value={taxProfile.tax_type_change_date ?? ""} onChange={(e) => updateProfile("tax_type_change_date", e.target.value || null)} /></div>
            {taxProfile.tax_type_change_date && <div className="field-row"><label htmlFor="tax-change-to">변경 후 과세유형</label><select id="tax-change-to" className="input" value={taxProfile.changed_to_tax_type ?? ""} onChange={(e) => updateProfile("changed_to_tax_type", (e.target.value || null) as TaxProfileApi["changed_to_tax_type"])}><option value="">선택</option><option value="general">일반과세</option><option value="simplified">간이과세</option></select></div>}
            <div className="field-row"><label htmlFor="suspension-start">휴업 시작일 (해당 시)</label><input id="suspension-start" className="input" type="date" value={taxProfile.suspension_periods[0]?.start_date ?? ""} onChange={(e) => updateProfile("suspension_periods", e.target.value ? [{ start_date: e.target.value, end_date: taxProfile.suspension_periods[0]?.end_date ?? e.target.value }] : [])} /></div>
            <div className="field-row"><label htmlFor="suspension-end">휴업 종료일</label><input id="suspension-end" className="input" type="date" value={taxProfile.suspension_periods[0]?.end_date ?? ""} onChange={(e) => updateProfile("suspension_periods", e.target.value ? [{ start_date: taxProfile.suspension_periods[0]?.start_date ?? e.target.value, end_date: e.target.value }] : [])} /></div>
            <div className="btn-row"><button className="btn btn--secondary" disabled={profileSaving} onClick={() => void saveProfile(false)}>저장</button><button className="btn btn--primary" disabled={profileSaving} onClick={() => void saveProfile(true)}>정보 확인 완료</button></div>
          </details>}</>;
}
