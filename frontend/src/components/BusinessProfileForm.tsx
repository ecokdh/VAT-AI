import { useEffect, useState } from "react";
import { isAxiosError } from "axios";
import { apiClient } from "../api/client";
import { getMe, validIndustryCode, type BusinessFilingInfo } from "../api/auth";
import { getTaxProfile, saveTaxProfile, type TaxProfileApi, type TaxProfileInput } from "../api/transactions";
import { BusinessFilingFields } from "./BusinessFilingFields";
import { TaxProfileFields } from "./TaxProfileFields";

type Profile = BusinessFilingInfo & { business_name: string | null; business_number: string | null; verified_tax_type: string | null; verification_status: string; declared_tax_type: string | null; entity_type: string | null; operating_industry: string | null; business_description: string | null; has_employees: boolean | null; onboarding_completed: boolean };
const PROFILE_KEYS = ["declared_tax_type", "entity_type", "operating_industry", "business_description", "has_employees"] as const;
const FILING_KEYS = ["business_address", "business_type", "business_item", "industry_code"] as const;
const pick = (p: Profile, keys: readonly (keyof Profile)[]) => Object.fromEntries(keys.map(k => [k, p[k]]));
const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
const REQ = <span className="field-req" aria-hidden="true">*</span>;

// 마이페이지 사업자 정보: 사업 프로필·과세기간·신고서 기재 정보를 저장 버튼 하나로 저장한다.
// 사업 프로필은 저장하면 기존 공제 분석을 다시 확인하므로, 바뀐 부분만 보낸다.
export function BusinessProfileForm() {
  const [p, setP] = useState<Profile | null>(null);
  const [tax, setTax] = useState<TaxProfileApi | null>(null);
  const [saved, setSaved] = useState<{ profile: Profile; tax: TaxProfileApi } | null>(null);
  const [taxType, setTaxType] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);
  useEffect(() => {
    Promise.all([apiClient.get<Profile>("/v2/business/profile"), getTaxProfile(), getMe()]).then(([{ data }, taxProfile, user]) => {
      setP(data); setTax(taxProfile); setSaved({ profile: data, tax: taxProfile });
      setTaxType(user.business?.tax_type_code === "02" ? "simplified" : user.business?.tax_type_code === "01" ? "general" : null);
    }).catch(() => setResult({ ok: false, text: "사업자 정보를 불러오지 못했어요." }));
  }, []);
  function update(key: keyof Profile, value: unknown) { setP(v => v && { ...v, [key]: value }); setResult(null); }
  // 값을 고쳐도 "확인했어요" 체크는 사용자가 직접 풀 때까지 유지한다(저장할 때 체크 상태 그대로 확인 처리).
  function updateTax<K extends keyof TaxProfileInput>(key: K, value: TaxProfileInput[K]) { setTax(v => v && { ...v, [key]: value }); setResult(null); }

  async function save() {
    if (!p || !tax || !saved) return;
    setBusy(true); setResult(null);
    let profile = saved.profile, taxProfile = saved.tax;
    try {
      const profileChanged = !same(pick(p, PROFILE_KEYS), pick(profile, PROFILE_KEYS));
      if (profileChanged) profile = (await apiClient.put<Profile>("/v2/business/profile", pick(p, PROFILE_KEYS))).data;
      if (!same(pick(p, FILING_KEYS), pick(profile, FILING_KEYS))) profile = (await apiClient.put<Profile>("/v2/business/filing-info", pick(p, FILING_KEYS))).data;
      // 사업 프로필 저장은 서버에서 확인 표시를 지우므로, 체크돼 있으면 과세기간 정보를 다시 보내 확인을 유지한다.
      if (!same(tax, taxProfile) || (profileChanged && tax.confirmed)) taxProfile = await saveTaxProfile(tax);
      setP(profile); setTax(taxProfile);
      setResult({ ok: true, text: "사업자 정보를 저장했어요." });
    } catch (error) {
      setResult({ ok: false, text: (isAxiosError(error) && error.response?.data?.error?.message) || "사업자 정보를 저장하지 못했어요. 입력값을 확인해 주세요." });
    } finally {
      setSaved({ profile, tax: taxProfile }); setBusy(false);
    }
  }

  if (!p || !tax) return <section className="account-business">{result && <p className="account-result account-result--error" role="alert">{result.text}</p>}</section>;
  return <section className="account-business">
    <h2 className="account-section-title">사업자 정보</h2>
    <p className="account-hint">바꾸면 기존 공제 분석을 다시 확인해요.</p>
    <dl className="account-info">
      <div><dt>상호</dt><dd>{p.business_name ?? "미확인"}</dd></div>
      <div><dt>사업자등록번호</dt><dd>{p.business_number ?? "미확인"}</dd></div>
      <div><dt>조회된 과세유형</dt><dd className="account-info__accent">{p.verified_tax_type ?? "미확인"}</dd></div>
    </dl>
    <fieldset disabled={busy}>
      <label className="form-field"><span className="form-field__label">현재 과세 유형{REQ}</span><select className="input" value={p.declared_tax_type ?? ""} onChange={e => update("declared_tax_type", e.target.value || null)}><option value="">미확인</option><option value="general">일반과세</option><option value="simplified">간이과세</option><option value="exempt">면세사업</option></select></label>
      <label className="form-field"><span className="form-field__label">사업자 형태{REQ}</span><select className="input" value={p.entity_type ?? ""} onChange={e => update("entity_type", e.target.value || null)}><option value="">아직 확인하지 못함</option><option value="individual">개인사업자</option><option value="corporation">법인사업자</option></select></label>
      <label className="form-field"><span className="form-field__label">실제 업종{REQ}</span><select className="input" value={p.operating_industry ?? ""} onChange={e => update("operating_industry", e.target.value || null)}><option value="">미확인</option>{[["food_service", "음식점"], ["cafe", "카페·베이커리"], ["retail", "도소매"], ["manufacturing", "제조업"], ["service", "서비스업"], ["other", "기타"]].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
      <label className="form-field"><span className="form-field__label">실제 하는 일<span className="field-opt">(선택)</span></span><textarea className="input" maxLength={1000} placeholder="예: 동네 카페 운영" value={p.business_description ?? ""} onChange={e => update("business_description", e.target.value || null)} /><span className="account-hint">공제 판별 때 거래 용도를 짐작하는 데 써요.</span></label>
      <label className="form-field"><span className="form-field__label">직원 유무<span className="field-opt">(선택)</span></span><select className="input" value={p.has_employees === null ? "" : p.has_employees ? "yes" : "no"} onChange={e => update("has_employees", e.target.value === "" ? null : e.target.value === "yes")}><option value="">미확인</option><option value="yes">직원 있음</option><option value="no">직원 없음</option></select></label>

      <h3 className="account-sub-title">과세기간 정보</h3>
      <TaxProfileFields taxProfile={tax} taxType={taxType} updateProfile={updateTax} />
      <BusinessFilingFields value={p} onChange={(key, value) => update(key, value)} />

      <label className="check-row account-confirm"><input type="checkbox" checked={tax.confirmed} onChange={e => { setTax({ ...tax, confirmed: e.target.checked }); setResult(null); }} />입력한 사업자 정보를 확인했어요.</label>
      <p className="account-hint">확인해야 세액 계산에 반영돼요.</p>
      <button type="button" className="btn btn--primary account-save" disabled={!validIndustryCode(p.industry_code)} onClick={() => void save()}>{busy ? "저장 중…" : "사업자 정보 저장"}</button>
      {result && <p className={`account-result ${result.ok ? "" : "account-result--error"}`} role={result.ok ? "status" : "alert"}>{result.ok && "✓ "}{result.text}</p>}
    </fieldset>
  </section>;
}
