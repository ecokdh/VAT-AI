import { PageHeader } from "../../components/PageHeader";
import { mockReport } from "../../mocks/report";
import { mockDeduction } from "../../mocks/deduction";
import { purchaseTotals } from "../../mocks/receipts";
import { useMaskedFormat } from "../../hooks/useMaskedFormat";

export function ReportPage() {
  const fmt = useMaskedFormat();
  return (
    <div className="page">
      <PageHeader title="부가가치세 신고서 생성" showAmountToggle />
      <div className="page__body">
        <div className="summary-card summary-card--primary" style={{ marginBottom: 16 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
            <div>
              <div className="summary-card__eyebrow">
                {mockReport.businessType.split(" · ")[0]} 일반과세자 · {mockReport.period.slice(0, 12)}
              </div>
              <div style={{ fontWeight: 800, fontSize: 18, marginTop: 4 }}>부가가치세 신고서 자동 생성 완료</div>
            </div>
            <span className="pill" style={{ background: "rgba(255,255,255,0.2)", color: "#fff", whiteSpace: "nowrap", flexShrink: 0 }}>
              국세청
            </span>
          </div>
        </div>

        <div className="card">
          <div className="card__title">👤 ① 사업자 기본 정보</div>
          <div className="field-row">
            <span className="field-row__label">상호 (법인명)</span>
            <span className="field-row__value">{mockReport.businessName}</span>
          </div>
          <div className="field-row">
            <span className="field-row__label">사업자등록번호</span>
            <span className="field-row__value">{mockReport.businessNumber}</span>
          </div>
          <div className="field-row">
            <span className="field-row__label">대표자 성명</span>
            <span className="field-row__value">{mockReport.representativeName}</span>
          </div>
          <div className="field-row">
            <span className="field-row__label">업태 / 종목</span>
            <span className="field-row__value">{mockReport.businessType}</span>
          </div>
          <div className="field-row">
            <span className="field-row__label">과세기간</span>
            <span className="field-row__value">{mockReport.period.match(/\(([^)]+)\)/)?.[1]}</span>
          </div>
          <div className="field-row">
            <span className="field-row__label">신고구분</span>
            <span className="field-row__value">확정신고</span>
          </div>
        </div>

        <div className="card">
          <div className="card__title">📈 ② 과세표준 및 매출세액</div>
          <div className="field-row">
            <span className="field-row__label">세금계산서 발급분 공급가액</span>
            <span className="field-row__value">{fmt.won(mockReport.taxBase)}</span>
          </div>
          <div className="field-row">
            <span className="field-row__label">세금계산서 발급분 세액</span>
            <span className="field-row__value">{fmt.won(mockReport.salesTax)}</span>
          </div>
          <div className="field-row">
            <span className="field-row__label">과세표준 합계</span>
            <span className="field-row__value field-row__value--total">{fmt.won(mockReport.taxBase)}</span>
          </div>
          <div className="field-row">
            <span className="field-row__label">매출세액 합계</span>
            <span className="field-row__value field-row__value--accent field-row__value--total">
              {fmt.won(mockReport.salesTax)}
            </span>
          </div>
        </div>

        <div className="card">
          <div className="card__title">📉 ③ 매입세액</div>
          <div className="field-row">
            <span className="field-row__label">세금계산서 수취분 공급가액</span>
            <span className="field-row__value">{fmt.won(purchaseTotals.supplyAmount)}</span>
          </div>
          <div className="field-row">
            <span className="field-row__label">세금계산서 수취분 세액</span>
            <span className="field-row__value">{fmt.won(purchaseTotals.vatAmount)}</span>
          </div>
          <div className="field-row">
            <span className="field-row__label">면세농산물 의제매입세액공제</span>
            <span className="field-row__value">−{fmt.won(mockDeduction.deductibleAmount)}</span>
          </div>
          <div className="field-row">
            <span className="field-row__label">의제매입세액 (2/102 적용)</span>
            <span className="field-row__value">{fmt.won(mockDeduction.deductibleAmount)}</span>
          </div>
          <div className="field-row">
            <span className="field-row__label">매입세액 합계</span>
            <span className="field-row__value field-row__value--total">{fmt.won(mockReport.purchaseTaxTotal)}</span>
          </div>
          <div className="field-row">
            <span className="field-row__label">공제세액 소계</span>
            <span className="field-row__value field-row__value--accent field-row__value--total">
              {fmt.won(mockReport.purchaseTaxTotal)}
            </span>
          </div>
        </div>

        <div className="card">
          <div className="card__title">⚖️ ④ 경감·공제세액</div>
          <div className="field-row">
            <span className="field-row__label">전자신고 세액공제</span>
            <span className="field-row__value">{fmt.won(mockReport.reductionTotal)}</span>
          </div>
          <div className="field-row">
            <span className="field-row__label">신용카드 발행 세액공제</span>
            <span className="field-row__value">0 원</span>
          </div>
          <div className="field-row">
            <span className="field-row__label">경감·공제세액 합계</span>
            <span className="field-row__value field-row__value--accent field-row__value--total">
              {fmt.won(mockReport.reductionTotal)}
            </span>
          </div>
        </div>

        <div className="card">
          <div className="card__title">ℹ️ ⑤ 가산세</div>
          <div className="field-row">
            <span className="field-row__label">세금계산서 지연 발급 가산세</span>
            <span className="field-row__value">0 원</span>
          </div>
          <div className="field-row">
            <span className="field-row__label">무신고 가산세</span>
            <span className="field-row__value">0 원</span>
          </div>
          <div className="field-row">
            <span className="field-row__label">가산세 합계</span>
            <span className="field-row__value field-row__value--accent field-row__value--total">
              {fmt.won(mockReport.additionalTaxTotal)}
            </span>
          </div>
        </div>

        <div className="card" style={{ background: "var(--color-primary-light)", border: "none" }}>
          <div className="card__title">🧮 ⑥ 최종 납부(환급)세액 계산</div>
          <div className="field-row">
            <span className="field-row__label">매출세액</span>
            <span className="field-row__value">+ {fmt.won(mockReport.salesTax)}</span>
          </div>
          <div className="field-row">
            <span className="field-row__label">매입세액 공제</span>
            <span className="field-row__value">− {fmt.won(mockReport.purchaseTaxTotal)}</span>
          </div>
          <div className="field-row">
            <span className="field-row__label">경감·공제세액</span>
            <span className="field-row__value">− {fmt.won(mockReport.reductionTotal)}</span>
          </div>
          <div className="field-row">
            <span className="field-row__label">가산세</span>
            <span className="field-row__value">+ {fmt.won(mockReport.additionalTaxTotal)}</span>
          </div>
          <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid rgba(61,90,254,0.2)" }}>
            <div className="field-row__label" style={{ color: "var(--color-primary-dark)", fontWeight: 700 }}>
              최종 납부세액
            </div>
            <div style={{ fontSize: 28, fontWeight: 800, color: "var(--color-primary)", marginTop: 4 }}>
              {fmt.won(mockReport.finalTax)}
            </div>
          </div>
        </div>

        <div className="banner banner--warning" style={{ margin: "16px 0" }}>
          <span>📅</span>
          <div>
            <div className="banner__title">신고·납부 기한</div>
            {mockReport.dueDate}
          </div>
        </div>

        <div className="card">
          <div className="card__title">📘 근거 법령</div>
          <div className="stack-gap-sm">
            <div>
              <span className="pill pill--primary" style={{ marginBottom: 6, display: "inline-block" }}>
                부가가치세법 제48조
              </span>
              <p style={{ fontSize: 13, color: "var(--color-text-muted)", margin: "4px 0 0", lineHeight: 1.5 }}>
                확정신고 및 납부: 사업자는 각 과세기간에 대한 과세표준과 세액을 그 과세기간 종료 후 25일 이내에 신고·납부하여야 한다.
              </p>
            </div>
            <div>
              <span className="pill pill--primary" style={{ marginBottom: 6, display: "inline-block" }}>
                부가가치세법 제42조
              </span>
              <p style={{ fontSize: 13, color: "var(--color-text-muted)", margin: "4px 0 0", lineHeight: 1.5 }}>
                의제매입세액: 음식점업 2/102 적용 (과세표준 2억 이하 개인사업자).
              </p>
            </div>
          </div>
        </div>

        <div className="stack-gap-sm" style={{ marginTop: 24 }}>
          <button className="btn btn--primary">국세청 홈택스 신고서 제출</button>
          <button className="btn btn--secondary">PDF로 저장하기</button>
        </div>
      </div>
    </div>
  );
}
