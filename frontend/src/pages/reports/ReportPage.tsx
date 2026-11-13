import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { isAxiosError } from "axios";
import { createVatReturnJob, downloadPdfJob, getAsyncJob, type AsyncJobApi, type VatReturnResult } from "../../api/transactions";
import { PageHeader } from "../../components/PageHeader";
import { useReviewOverview, periodLabel, periodOptions } from "../../hooks/useReviewOverview";
import { formatWon } from "../../utils/format";
import "../../styles/report.css";

export function ReportPage() {
  const view=useReviewOverview();
  const {period,estimate}=view;
  const navigate=useNavigate();
const [error,setError]=useState("");
  const [pdfMessage,setPdfMessage]=useState("");
  const [reviewedKey,setReviewedKey]=useState("");
  const reviewKey=JSON.stringify([period,estimate,view.readiness,view.transactions]);
  const reviewed=reviewedKey===reviewKey;
  const canGenerate=!view.loading&&!view.error&&reviewed;
  const setReviewed=(value:boolean)=>setReviewedKey(value?reviewKey:"");
  const [returnBusy,setReturnBusy]=useState(false);
  const [returnResult,setReturnResult]=useState<VatReturnResult|null>(null);

  // 모델 검증까지 하면 몇 분 걸릴 수 있어 최대 4분 기다린다.
  async function waitForJob(job: AsyncJobApi, seconds: number) {
    for (let i = 0; i < seconds && (job.status === "PENDING" || job.status === "PROCESSING"); i += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 1000));
      job = await getAsyncJob(job.id);
    }
    return job;
  }
  function saveBlob(blob: Blob, name: string) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url; link.download = name; link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  async function createVatReturn() {
    if (!period || returnBusy || !canGenerate) return;
    setReturnBusy(true); setReturnResult(null); setError("");
    setPdfMessage("부가세 신고서를 만들고 있습니다. 검증 서버가 켜져 있으면 몇 분 걸릴 수 있어요.");
    try {
      const job = await waitForJob(await createVatReturnJob(period), 240);
      if (job.status === "FAILED") throw new Error(job.error_message ?? "신고서 생성에 실패했습니다.");
      if (job.status !== "COMPLETED" || !job.result_json) { setPdfMessage("작업은 계속 처리 중입니다. 잠시 후 다시 시도해 주세요."); return; }
      saveBlob(await downloadPdfJob(job.id), `부가세신고서-${period}.pdf`);
      setReturnResult(JSON.parse(job.result_json));
      setPdfMessage("신고서 PDF를 받았습니다. 신고 준비용이며 홈택스에는 제출되지 않습니다.");
    } catch (cause) {
      const message = isAxiosError(cause) ? cause.response?.data?.error?.message : undefined;
      setError(message ?? (cause instanceof Error ? cause.message : "신고서 생성에 실패했습니다."));
      setPdfMessage("");
    } finally { setReturnBusy(false); }
  }

  const amount=view.loading?"불러오는 중":view.salesPending?"매출 확인 필요":estimate?.payable_estimate==null?"확인 필요":formatWon(estimate.payable_estimate);
  return <div className="page qa-page report-page"><PageHeader title="신고서 생성"/><main className="page__body report-body">
    <div>
      <p className="eyebrow muted">부가가치세 신고 준비</p><h1 className="screen-title">신고할 내용을 확인하세요</h1>
      <label className="form-field report-period"><span className="form-field__label">신고 대상 기간</span><select className="input" value={period} onChange={e=>{view.setPeriod(e.target.value);setReviewed(false);}}>{periodOptions(view.user?.business?.tax_type_code==="02").map(p=><option key={p} value={p}>{periodLabel(p)}</option>)}</select></label>
    </div>
    {(error || view.error) && <p className="banner banner--error" role="alert">{error || view.error}</p>}
    <section className="report-hero" aria-live="polite"><span className="report-hero__label">예상 납부세액</span><strong className="report-hero__amount">{amount}</strong><span className="report-hero__caption">확정 거래 기준 · 검토를 위한 참고용 추정치</span></section>
    {estimate ? <details className="report-card report-details"><summary>계산 내역 자세히 보기</summary>{[["매출세액",estimate.output_vat],["일반 매입 공제액",estimate.eligible_input_vat],["의제매입 공제액",estimate.deemed_input_vat],["신용카드 발행세액공제",estimate.card_issuance_credit]].map(([label,value])=><div className="report-details__row" key={String(label)}><span>{label}</span><strong>{value==null?"확인 필요":formatWon(Number(value))}</strong></div>)}{estimate.notes.map(note=><p className="report-details__note" key={note}>{note}</p>)}</details>
      : !view.loading && <button className="banner banner--warning" onClick={()=>navigate("/account")}>사업자 과세유형 및 설정을 확인해 주세요 ›</button>}
    <label className="report-check"><input type="checkbox" checked={reviewed} disabled={view.loading} onChange={e=>setReviewed(e.target.checked)}/>예상세액 및 계산 근거를 검토했습니다.</label>
    <button className="btn btn--primary report-cta" disabled={returnBusy || !canGenerate} onClick={()=>void createVatReturn()}>{returnBusy?"신고서 만드는 중…":"부가세 신고서 PDF 생성"}</button>
    {pdfMessage && <p className="report-footnote" role="status">{pdfMessage}</p>}
    {returnResult && <section className="report-card vat-return-result" role="status">
      <h2 className="section-title">신고서 확인 사항</h2>
      <p className={`banner ${returnResult.verification.status === "mismatch" ? "banner--warning" : "banner--info"}`}>{returnResult.verification.message}</p>
      {returnResult.verification.mismatches?.map(m => <div className="report-details__row" key={m.field}><span>{m.label}</span><span>넣은 값 {m.expected || "(빈칸)"} · 읽은 값 {m.read || "(빈칸)"}</span></div>)}
      <ul>{returnResult.notes.map(note => <li key={note} className="muted">{note}</li>)}</ul>
    </section>}
  </main></div>;
}
