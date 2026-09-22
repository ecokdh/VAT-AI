import { useNavigate } from "react-router-dom";
import { PageHeader } from "../../components/PageHeader";
import { mockOcrResult } from "../../mocks/ocr";
import { mockDeduction } from "../../mocks/deduction";
import { formatDate } from "../../utils/format";
import { useMaskedFormat } from "../../hooks/useMaskedFormat";

export function AnalysisResultPage() {
  const navigate = useNavigate();
  const fmt = useMaskedFormat();

  return (
    <div className="page">
      <PageHeader title="AI 세액 분석 결과" showAmountToggle />
      <div className="page__body">
        <div
          className="summary-card summary-card--primary"
          style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}
        >
          <div>
            <div className="summary-card__eyebrow">Naver OCR + ChatGPT 4o 분석</div>
            <div style={{ fontWeight: 800, fontSize: 18, marginTop: 4 }}>의제매입세액 자동 분석 완료</div>
          </div>
          <span className="pill" style={{ background: "rgba(255,255,255,0.2)", color: "#fff", whiteSpace: "nowrap", flexShrink: 0 }}>
            GPT-4o
          </span>
        </div>

        <div className="card">
          <div className="card__title" style={{ justifyContent: "space-between" }}>
            <span>🔗 OCR 추출 정보 요약</span>
            <span className="pill pill--primary">면세매입</span>
          </div>
          <div className="field-row">
            <span className="field-row__label">공급자</span>
            <span className="field-row__value">{mockOcrResult.supplierName}</span>
          </div>
          <div className="field-row">
            <span className="field-row__label">품목</span>
            <span className="field-row__value">{mockOcrResult.itemName}</span>
          </div>
          <div className="field-row">
            <span className="field-row__label">면세 공급가액</span>
            <span className="field-row__value">{fmt.won(mockOcrResult.supplyAmount)}</span>
          </div>
          <div className="field-row">
            <span className="field-row__label">부가가치세</span>
            <span className="field-row__value">0 원 (면세품목)</span>
          </div>
          <div className="field-row">
            <span className="field-row__label">발행일자</span>
            <span className="field-row__value">{formatDate(mockOcrResult.issuedAt)}</span>
          </div>
        </div>

        <div className="card">
          <div className="card__title">📘 의제매입세액 계산 과정</div>
          <div className="banner banner--info" style={{ marginBottom: 16 }}>
            <div>
              <div className="banner__title">AI 판단 근거</div>
              {mockDeduction.reason}
            </div>
          </div>
          <div className="field-row">
            <span className="field-row__label">① 면세 매입 공급가액</span>
            <span className="field-row__value">{fmt.won(mockDeduction.exemptSupplyAmount)}</span>
          </div>
          <div className="field-row">
            <span className="field-row__label">② 적용 공제율 (음식점업 과세표준 2억 이하)</span>
            <span className="field-row__value field-row__value--accent">{mockDeduction.applicableRate}</span>
          </div>
          <div className="field-row">
            <span className="field-row__label">③ 의제매입세액 = ① × ②</span>
            <span className="field-row__value">{fmt.won(mockDeduction.deductibleAmount)}</span>
          </div>
          <div className="field-row">
            <span className="field-row__label">공제 가능 의제매입세액</span>
            <span className="field-row__value field-row__value--accent field-row__value--total">
              {fmt.won(mockDeduction.deductibleAmount)}
            </span>
          </div>
        </div>

        <div className="card">
          <div className="card__title">📖 관련 법령 근거</div>
          <div className="stack-gap-sm">
            {mockDeduction.relatedLaws.map((law) => (
              <div key={law.title}>
                <span className="pill pill--primary" style={{ marginBottom: 6, display: "inline-block" }}>
                  {law.title}
                </span>
                <p style={{ fontSize: 13, color: "var(--color-text-muted)", margin: "4px 0 0", lineHeight: 1.5 }}>{law.content}</p>
              </div>
            ))}
          </div>
        </div>

        {mockDeduction.capWarning && (
          <div className="banner banner--warning" style={{ marginTop: 4, marginBottom: 20 }}>
            <span>⚠️</span>
            <div>
              <div className="banner__title">공제 한도 주의</div>
              {mockDeduction.capWarning}
            </div>
          </div>
        )}

        <div className="stack-gap-sm">
          <button className="btn btn--primary" onClick={() => navigate("/storage/purchase")}>
            의제매입세액 {fmt.won(mockDeduction.deductibleAmount)} 반영하기
          </button>
          <button className="btn btn--secondary">결과 상세 내보내기</button>
        </div>
      </div>
    </div>
  );
}
