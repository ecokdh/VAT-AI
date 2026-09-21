import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";

const STEPS = [
  { label: "이미지 글자 세그먼트 분석", status: "완료" },
  { label: "공급가액 및 부가가치세 인식", status: "완료" },
  { label: "구매처(공급받는 자) 정보 추출", status: "추출 중..." },
];

export function OcrProcessingPage() {
  const navigate = useNavigate();
  const { id } = useParams();

  useEffect(() => {
    const timer = setTimeout(() => navigate(`/receipts/${id}/edit`, { replace: true }), 1600);
    return () => clearTimeout(timer);
  }, [id, navigate]);

  return (
    <div className="page">
      <div className="page__body" style={{ paddingTop: 48, textAlign: "center" }}>
        <div
          style={{
            width: 88,
            height: 88,
            borderRadius: "50%",
            background: "var(--color-primary-light)",
            margin: "0 auto 20px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 34,
            animation: "spin 1.4s linear infinite",
          }}
        >
          ✨
        </div>
        <div style={{ fontSize: 20, fontWeight: 800 }}>Naver CLOVA OCR 분석 중</div>
        <div className="muted" style={{ fontSize: 13, marginTop: 8 }}>
          사진 속 세액 및 필수 정보를 정밀 추출하고 있습니다
        </div>

        <div
          style={{
            marginTop: 28,
            borderRadius: 20,
            overflow: "hidden",
            position: "relative",
            background: "#e9e9ee",
            aspectRatio: "4 / 5",
          }}
        >
          <div
            style={{
              position: "absolute",
              inset: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 48,
              color: "#c3c5d1",
            }}
          >
            🧾
          </div>
          <div
            style={{
              position: "absolute",
              left: 0,
              right: 0,
              bottom: 0,
              background: "rgba(0,0,0,0.7)",
              color: "#fff",
              padding: "12px 16px",
              display: "flex",
              justifyContent: "space-between",
              fontSize: 13,
            }}
          >
            <span>tax_invoice_2024_01.jpg</span>
            <span style={{ color: "#7ea0ff", fontWeight: 700 }}>68% 완료</span>
          </div>
        </div>

        <div className="stack-gap-sm" style={{ marginTop: 24, textAlign: "left" }}>
          {STEPS.map((step) => (
            <div key={step.label} className="field-row" style={{ background: "var(--color-surface-muted)", padding: "12px 16px", borderRadius: 12, border: "1px solid var(--color-divider)" }}>
              <span className="field-row__label" style={{ color: "var(--color-text)" }}>
                {step.status === "완료" ? "✅" : "🔵"} {step.label}
              </span>
              <span className="field-row__value--accent" style={{ fontWeight: 700 }}>
                {step.status}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
