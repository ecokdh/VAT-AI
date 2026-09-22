import { useState } from "react";
import { isAxiosError } from "axios";
import { useNavigate } from "react-router-dom";
import { PageHeader } from "../../components/PageHeader";
import { mockUser } from "../../mocks/user";
import { register } from "../../api/auth";

export function SignupPage() {
  const navigate = useNavigate();
  const [businessNumber, setBusinessNumber] = useState(mockUser.businessNumber);
  const [businessVerified, setBusinessVerified] = useState(false);
  const [businessName, setBusinessName] = useState("");
  const [email, setEmail] = useState("");
  const [emailChecked, setEmailChecked] = useState(false);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  function handleVerifyBusiness() {
    // 스켈레톤 단계: 국세청 공공데이터포털 실시간 조회를 흉내내는 목업 동작
    setBusinessVerified(true);
    setBusinessName(mockUser.businessName);
  }

  function handleCheckEmail() {
    setEmailChecked(true);
  }

  async function handleSignup() {
    setError("");
    setIsSubmitting(true);
    try {
      // 스켈레톤 단계: User 엔티티에 사업자 필드가 아직 없어 사업장명을 name으로 전달
      const { access_token } = await register(email, password, businessName);
      localStorage.setItem("access_token", access_token);
      navigate("/dashboard");
    } catch (e) {
      const message = isAxiosError(e) ? e.response?.data?.error?.message : undefined;
      setError(message ?? "회원가입에 실패하였습니다.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="page">
      <PageHeader title="사업자 회원가입" onBack={() => navigate("/login")} />
      <div className="page__body">
        <div style={{ margin: "8px 0 24px" }}>
          <div style={{ fontSize: 22, fontWeight: 800, lineHeight: 1.35 }}>
            부가가치세 신고,
            <br />
            TAX-AI와 시작해 보세요
          </div>
          <div className="muted" style={{ marginTop: 8, fontSize: 13 }}>
            공공데이터포털 실시간 검증으로 더 정확하게
          </div>
        </div>

        <div className="form-field">
          <label className="form-field__label">사업자등록번호</label>
          <div className="form-field__input-row">
            <input
              className="input"
              value={businessNumber}
              onChange={(e) => setBusinessNumber(e.target.value)}
            />
            <button className="btn btn--secondary btn--sm" style={{ width: 110, flexShrink: 0 }} onClick={handleVerifyBusiness}>
              실시간 조회
            </button>
          </div>
          {businessVerified && <div className="form-field__hint">국세청(공공데이터포털) 등록 확인 완료 (일반과세자)</div>}
        </div>

        <div className="form-field">
          <label className="form-field__label">사업장명</label>
          <input className="input" value={businessName} onChange={(e) => setBusinessName(e.target.value)} />
        </div>

        <div className="form-field">
          <label className="form-field__label">대표자 이메일</label>
          <div className="form-field__input-row">
            <input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
            <button className="btn btn--secondary btn--sm" style={{ width: 100, flexShrink: 0 }} onClick={handleCheckEmail}>
              중복 확인
            </button>
          </div>
          {emailChecked && <div className="form-field__hint">사용 가능한 이메일입니다</div>}
        </div>

        <div className="form-field">
          <label className="form-field__label">비밀번호 설정</label>
          <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>

        <div className="banner banner--info" style={{ margin: "20px 0 24px" }}>
          <span>🛡️</span>
          <div>공공데이터포털 사업자정보 API 검증을 마쳤습니다. 입력된 사업장 정보는 암호화되어 안전하게 보관됩니다.</div>
        </div>

        {error && (
          <div className="banner banner--error" style={{ margin: "0 0 16px" }}>
            <span>⚠️</span>
            <div>{error}</div>
          </div>
        )}

        <button className="btn btn--primary" onClick={handleSignup} disabled={isSubmitting}>
          {isSubmitting ? "가입 처리 중..." : "휴대폰 본인 인증"}
        </button>
      </div>
    </div>
  );
}
