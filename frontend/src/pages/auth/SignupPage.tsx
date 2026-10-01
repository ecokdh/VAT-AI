import { useRef, useState } from "react";
import { isAxiosError } from "axios";
import { useNavigate } from "react-router-dom";
import { PageHeader } from "../../components/PageHeader";
import { register } from "../../api/auth";
import { verifyBusiness, type BusinessVerificationResponse } from "../../api/business";

const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function normalizedBusinessNumber(value: string) {
  return value.replace(/[\s-]/g, "");
}

function validBusinessNumber(value: string) {
  return /^[0-9\s-]+$/.test(value) && /^[0-9]{10}$/.test(normalizedBusinessNumber(value));
}

function businessError(error: unknown) {
  if (!isAxiosError(error)) return "사업자정보 조회에 실패했습니다. 잠시 후 다시 시도해 주세요.";
  if (!error.response) return "사업자정보 조회 서비스에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.";
  const code = error.response?.data?.error?.code;
  switch (code) {
    case "VALIDATION_ERROR":
      return "사업자등록번호는 숫자 10자리로 입력해 주세요.";
    case "BUSINESS_NOT_REGISTERED":
      return "국세청에 등록된 사업자정보를 찾을 수 없습니다.";
    case "BUSINESS_API_TIMEOUT":
      return "국세청 조회 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.";
    case "BUSINESS_API_NOT_CONFIGURED":
    case "BUSINESS_API_AUTH_ERROR":
    case "BUSINESS_API_QUOTA_EXCEEDED":
      return "사업자정보 조회 서비스를 현재 이용할 수 없습니다. 잠시 후 다시 시도해 주세요.";
    default:
      return "사업자정보 조회에 실패했습니다. 잠시 후 다시 시도해 주세요.";
  }
}

export function SignupPage() {
  const navigate = useNavigate();
  const verificationRun = useRef(0);
  const [name, setName] = useState("");
  const [businessName, setBusinessName] = useState("");
  const [businessNumber, setBusinessNumber] = useState("");
  const [verification, setVerification] = useState<BusinessVerificationResponse | null>(null);
  const [isVerifying, setIsVerifying] = useState(false);
  const [verificationError, setVerificationError] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirmation, setPasswordConfirmation] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const businessVerified = verification?.verified === true
    && verification.business_number === normalizedBusinessNumber(businessNumber);
  const passwordValid = password.length > 0 && new TextEncoder().encode(password).length <= 72;
  const canSubmit = name.trim().length > 0
    && businessName.trim().length > 0
    && validBusinessNumber(businessNumber)
    && businessVerified
    && emailPattern.test(email.trim())
    && passwordValid
    && passwordConfirmation === password
    && !isVerifying
    && !isSubmitting;

  function handleBusinessNumberChange(value: string) {
    verificationRun.current += 1;
    setBusinessNumber(value);
    setVerification(null);
    setVerificationError("");
    setIsVerifying(false);
  }

  async function handleVerifyBusiness() {
    if (!validBusinessNumber(businessNumber)) {
      setVerificationError("사업자등록번호는 숫자 10자리로 입력해 주세요.");
      return;
    }
    const run = ++verificationRun.current;
    setVerification(null);
    setVerificationError("");
    setIsVerifying(true);
    try {
      const result = await verifyBusiness(businessNumber);
      if (run !== verificationRun.current) return;
      if (!result.verified || result.business_number !== normalizedBusinessNumber(businessNumber)) {
        setVerificationError("사업자정보 조회 결과를 확인할 수 없습니다. 다시 시도해 주세요.");
        return;
      }
      setVerification(result);
    } catch (requestError) {
      if (run === verificationRun.current) setVerificationError(businessError(requestError));
    } finally {
      if (run === verificationRun.current) setIsVerifying(false);
    }
  }

  async function handleSignup() {
    if (!canSubmit) return;
    setError("");
    setIsSubmitting(true);
    try {
      const { access_token } = await register({
        email: email.trim(),
        password,
        name: name.trim(),
        business_name: businessName.trim(),
        business_number: normalizedBusinessNumber(businessNumber),
      });
      localStorage.setItem("access_token", access_token);
      navigate("/dashboard");
    } catch (requestError) {
      const code = isAxiosError(requestError) ? requestError.response?.data?.error?.code : undefined;
      if (code === "EMAIL_ALREADY_EXISTS") {
        setError("이미 가입된 이메일입니다.");
      } else if (typeof code === "string" && code.startsWith("BUSINESS_")) {
        setVerification(null);
        setVerificationError(businessError(requestError));
        setError("사업자정보를 다시 확인해 주세요.");
      } else {
        setError("회원가입에 실패했습니다. 입력 내용을 확인하고 다시 시도해 주세요.");
      }
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
            부가가치세 신고,<br />TAX-AI와 시작해 보세요
          </div>
          <div className="muted" style={{ marginTop: 8, fontSize: 13 }}>
            국세청 사업자등록 상태조회로 현재 상태를 확인합니다.
          </div>
        </div>

        <div className="form-field">
          <label className="form-field__label" htmlFor="signup-name">사용자 이름</label>
          <input id="signup-name" className="input" value={name} onChange={(e) => setName(e.target.value)} />
        </div>

        <div className="form-field">
          <label className="form-field__label" htmlFor="signup-business-name">상호명</label>
          <input id="signup-business-name" className="input" value={businessName} onChange={(e) => setBusinessName(e.target.value)} />
          <div className="form-field__hint">상호명은 직접 입력한 정보이며 국세청 상태조회로 확인되지 않습니다.</div>
        </div>

        <div className="form-field">
          <label className="form-field__label" htmlFor="signup-business-number">사업자등록번호</label>
          <div className="form-field__input-row">
            <input
              id="signup-business-number"
              className="input"
              inputMode="numeric"
              value={businessNumber}
              onChange={(e) => handleBusinessNumberChange(e.target.value)}
            />
            <button className="btn btn--secondary btn--sm" style={{ width: 110, flexShrink: 0 }} onClick={handleVerifyBusiness} disabled={isVerifying || !validBusinessNumber(businessNumber)}>
              {isVerifying ? "조회 중..." : "사업자 확인"}
            </button>
          </div>
          {businessNumber && !validBusinessNumber(businessNumber) && (
            <div className="form-field__hint form-field__hint--error">사업자등록번호는 숫자 10자리로 입력해 주세요.</div>
          )}
          {verificationError && <div className="form-field__hint form-field__hint--error" role="alert">{verificationError}</div>}
          {businessVerified && verification && (
            <div className="form-field__hint" role="status">
              국세청 상태조회 완료 · {verification.business_status} · {verification.tax_type}
              {verification.end_date && ` · 폐업일자 ${verification.end_date}`}
            </div>
          )}
        </div>

        {businessVerified && verification?.business_status_code === "02" && (
          <div className="banner banner--warning" style={{ marginBottom: 16 }} role="status">
            현재 휴업 상태로 조회됩니다. 가입은 가능하지만 사업자 상태가 이후 세무 검토에 참고됩니다.
          </div>
        )}
        {businessVerified && verification?.business_status_code === "03" && (
          <div className="banner banner--error" style={{ marginBottom: 16 }} role="status">
            현재 폐업 상태로 조회됩니다. 가입은 가능하지만 사업자 상태가 이후 세무 검토에 참고됩니다.
          </div>
        )}

        <div className="form-field">
          <label className="form-field__label" htmlFor="signup-email">이메일</label>
          <input id="signup-email" className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="form-field">
          <label className="form-field__label" htmlFor="signup-password">비밀번호</label>
          <input id="signup-password" className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
          <div className="form-field__hint">UTF-8 기준 72바이트 이하로 입력해 주세요.</div>
        </div>
        <div className="form-field">
          <label className="form-field__label" htmlFor="signup-password-confirmation">비밀번호 확인</label>
          <input id="signup-password-confirmation" className="input" type="password" value={passwordConfirmation} onChange={(e) => setPasswordConfirmation(e.target.value)} />
          {passwordConfirmation && passwordConfirmation !== password && (
            <div className="form-field__hint form-field__hint--error">비밀번호가 일치하지 않습니다.</div>
          )}
        </div>

        {error && <div className="banner banner--error" style={{ margin: "0 0 16px" }} role="alert">{error}</div>}
        <button className="btn btn--primary" onClick={handleSignup} disabled={!canSubmit}>
          {isSubmitting ? "가입 처리 중..." : "회원가입"}
        </button>
      </div>
    </div>
  );
}
