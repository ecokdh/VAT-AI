import { TaxProfileFields } from "./TaxProfileFields";
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

  function updateProfile<K extends keyof TaxProfileInput>(key: K, value: TaxProfileInput[K]) {
    setTaxProfile((current) => current ? { ...current, [key]: value, confirmed: false } : current);
  }


return <>{message && <p className="banner banner--info" role="status">{message}</p>}{taxProfile &&           <details className="card" style={{ marginBottom: 16 }}>
            <summary style={{ cursor: "pointer", fontWeight: 600 }}>2026 사업자·과세기간 정보 {taxProfile.confirmed ? "(확인 완료)" : "(확인 필요)"}</summary>
            <p className="muted">입력한 값은 확인 완료 후 계산에 사용됩니다. 불명확한 거래는 자동으로 추정하지 않습니다.</p>
            <TaxProfileFields taxProfile={taxProfile} taxType={taxType} updateProfile={updateProfile}/>
            <div className="btn-row"><button className="btn btn--secondary" disabled={profileSaving} onClick={() => void saveProfile(false)}>저장</button><button className="btn btn--primary" disabled={profileSaving} onClick={() => void saveProfile(true)}>정보 확인 완료</button></div>
          </details>}</>;
}
