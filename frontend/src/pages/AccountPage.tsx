import { useEffect, useState } from "react";
import { getMe, type AuthUser } from "../api/auth";
import { PageHeader } from "../components/PageHeader";

export function AccountPage() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { getMe().then(setUser).catch(() => setError("내 정보를 불러오지 못했습니다. 다시 로그인해 주세요.")); }, []);
  return <div className="page"><PageHeader title="내 정보" /><div className="page__body">
    {error && <p role="alert">{error}</p>}
    {user ? <div className="card">{[["이름", user.name], ["이메일", user.email], ["사업장", user.business?.business_name], ["사업자번호", user.business?.business_number], ["사업 상태", user.business?.business_status], ["과세유형", user.business?.tax_type]].map(([label, value]) => <div className="field-row" key={label}><span className="muted">{label}</span><strong>{value ?? "미확인"}</strong></div>)}</div> : !error && <p role="status">정보를 불러오는 중입니다.</p>}
  </div></div>;
}

export function AboutPage() {
  return <div className="page"><PageHeader title="서비스 정보" /><div className="page__body"><div className="card"><h2>VAT-AI</h2><p>증빙을 모으고 거래 내용을 확인해 부가가치세 신고를 준비하는 서비스입니다.</p><p>매입 거래를 선택해 공제 분석을 요청할 수 있습니다. 확인이 필요한 결과는 예상 공제액에서 제외됩니다.</p><p className="muted">국세청 조회는 사업자 상태와 과세유형을 확인합니다. 상호·대표자 진위확인이나 홈택스 자동 신고를 수행하지 않습니다.</p></div></div></div>;
}
