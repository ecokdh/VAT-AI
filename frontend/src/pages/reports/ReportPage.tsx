import { useEffect, useState } from "react";
import { isAxiosError } from "axios";
import { getMe } from "../../api/auth";
import { createPdfJob, downloadPdfJob, getAsyncJob, getTaxEstimate, type TaxEstimateApi } from "../../api/transactions";
import { PageHeader } from "../../components/PageHeader";

const won = (value: number | null) => value == null ? "확인 필요" : `${value.toLocaleString()}원`;

export function ReportPage() {
  const [estimate, setEstimate] = useState<TaxEstimateApi | null>(null);
  const [period, setPeriod] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [pdfBusy, setPdfBusy] = useState(false);
  const [pdfMessage, setPdfMessage] = useState("");

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const user = await getMe();
        const taxType = user.business?.tax_type_code === "01" ? "general" : user.business?.tax_type_code === "02" ? "simplified" : null;
        if (!taxType) throw new Error("국세청 과세유형 확인이 필요합니다.");
        const nextPeriod = taxType === "simplified" ? "2026-YEAR" : "2026-H1";
        const result = await getTaxEstimate(nextPeriod);
        if (active) { setPeriod(nextPeriod); setEstimate(result); }
      } catch (cause) {
        if (!active) return;
        const message = isAxiosError(cause) ? cause.response?.data?.error?.message : undefined;
        setError(message ?? (cause instanceof Error ? cause.message : "예상 세액을 불러오지 못했습니다."));
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => { active = false; };
  }, []);

  async function createReviewPdf() {
    if (!period || pdfBusy) return;
    setPdfBusy(true);
    setPdfMessage("검토용 PDF 작업을 시작했습니다.");
    setError("");
    try {
      let job = await createPdfJob(period);
      for (let attempt = 0; attempt < 60 && (job.status === "PENDING" || job.status === "PROCESSING"); attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
        job = await getAsyncJob(job.id);
      }
      if (job.status === "FAILED") throw new Error(job.error_message ?? "PDF 생성에 실패했습니다.");
      if (job.status !== "COMPLETED") {
        setPdfMessage("작업은 계속 처리 중입니다. 잠시 후 다시 시도해 주세요.");
        return;
      }
      const blob = await downloadPdfJob(job.id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `vat-ai-review-${period}.pdf`;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setPdfMessage("검토용 PDF를 다운로드했습니다.");
    } catch (cause) {
      const message = isAxiosError(cause) ? cause.response?.data?.error?.message : undefined;
      setError(message ?? (cause instanceof Error ? cause.message : "PDF 생성에 실패했습니다."));
      setPdfMessage("");
    } finally {
      setPdfBusy(false);
    }
  }

  return (
    <div className="page">
      <PageHeader title="신고 전 검토 자료" showAmountToggle />
      <div className="page__body">
        <div className="banner banner--warning" style={{ marginBottom: 16 }}>
          <span>안내</span><div>이 자료는 사업자의 검토를 위한 예상치이며 세무 신고서가 아닙니다. VAT-AI는 홈택스에 신고하거나 제출하지 않습니다.</div>
        </div>
        {error && <div className="banner banner--error" role="alert">{error}</div>}
        {loading && <div className="center-note">2026년 거래를 계산하고 있습니다.</div>}
        {estimate && <>
          <section className="summary-card summary-card--primary" style={{ marginBottom: 16 }}>
            <div className="summary-card__eyebrow">{estimate.tax_type === "general" ? "일반과세자" : "간이과세자"} · {period === "2026-YEAR" ? "2026년 연간" : period === "2026-H1" ? "2026년 1기" : "2026년 2기"}</div>
            <div style={{ fontWeight: 800, fontSize: 18, marginTop: 4 }}>예상 납부세액 {won(estimate.payable_estimate)}</div>
            <div style={{ marginTop: 8 }}>계산 상태: {estimate.status} · 검토 {estimate.caution_transaction_count}건 · 미계산 {estimate.uncalculated_transaction_count}건</div>
          </section>
          <section className="card">
            <div className="card__title">2026년 예상 세액</div>
            <div className="field-row"><span className="field-row__label">매출세액</span><span className="field-row__value">{won(estimate.output_vat)}</span></div>
            <div className="field-row"><span className="field-row__label">일반 매입 공제액</span><span className="field-row__value">{won(estimate.eligible_input_vat)}</span></div>
            <div className="field-row"><span className="field-row__label">의제매입세액공제</span><span className="field-row__value">{won(estimate.deemed_input_vat)}</span></div>
            <div className="field-row"><strong>예상 납부세액</strong><strong>{won(estimate.payable_estimate)}</strong></div>
          </section>
          <section className="card" style={{ marginTop: 12 }}>
            <div className="card__title">검토할 내용</div>
            {estimate.notes.length ? estimate.notes.map((note) => <p key={note}>{note}</p>) : <p>현재 계산에 포함되지 않은 안내가 없습니다.</p>}
          </section>
          <button className="btn btn--primary" style={{ marginTop: 16 }} disabled={pdfBusy} onClick={() => void createReviewPdf()}>{pdfBusy ? "PDF 생성 중…" : "검토용 PDF 만들기"}</button>
          {pdfMessage && <p className="muted" role="status">{pdfMessage}</p>}
        </>}
      </div>
    </div>
  );
}
