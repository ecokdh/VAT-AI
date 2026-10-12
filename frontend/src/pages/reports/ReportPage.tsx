import { FilingPeriodSelect } from "../../components/FilingPeriodSelect";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { isAxiosError } from "axios";
import { createPdfJob, downloadPdfJob, getAsyncJob } from "../../api/transactions";
import { PageHeader } from "../../components/PageHeader";
import { useReviewOverview } from "../../hooks/useReviewOverview";
import { useMaskedFormat } from "../../hooks/useMaskedFormat";

export function ReportPage() {
  const view=useReviewOverview();
  const {period,estimate}=view;
  const navigate=useNavigate();
  const go = (path: string) => navigate(`${path}${path.includes("?") ? "&" : "?"}period=${period}`);
  const fmt=useMaskedFormat();
  const [error,setError]=useState("");
  const [pdfBusy,setPdfBusy]=useState(false);
  const [pdfMessage,setPdfMessage]=useState("");
  const [reviewed,setReviewed]=useState(false);

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


  return <div className="page qa-page"><PageHeader title="신고 전 검토" showAmountToggle/><main className="page__body">
    <p className="eyebrow muted">부가가치세 신고 준비</p><h1 className="screen-title">신고할 내용을 확인하세요</h1><p className="muted">확정 거래와 공제 분석을 바탕으로 신고 전 확인사항을 정리했어요.</p>
    <FilingPeriodSelect {...view}/>
    {(error || view.error) && <p className="banner banner--error" role="alert">{error || view.error}</p>}
    {view.loading && <p role="status">신고 준비 상태를 불러오는 중입니다.</p>}
    <section className="report-total"><small className="muted">예상 납부세액</small><strong>{estimate?.payable_estimate==null?"확인 필요":fmt.won(estimate.payable_estimate)}</strong><p className="muted">확정 거래 기준 · 검토를 위한 참고용 추정치</p></section>
    {estimate ? <details className="card"><summary>계산 내역 자세히 보기</summary>{[["매출세액",estimate.output_vat],["일반 매입 공제액",estimate.eligible_input_vat],["의제매입 공제액",estimate.deemed_input_vat]].map(([label,value])=><div className="field-row" key={String(label)}><span>{label}</span><strong>{value==null?"확인 필요":fmt.won(Number(value))}</strong></div>)}{estimate.notes.map(note=><p className="muted" key={note}>{note}</p>)}</details> : <button className="banner banner--warning" onClick={()=>navigate("/account")}>사업자 과세유형 및 설정을 확인해 주세요 ›</button>}
    {view.period ? <section className="card overview-card"><h2 className="section-title">신고 준비 현황</h2><div className="stat-grid">{[["전체 거래",view.total],["확인 필요",view.unconfirmed],["공제 검토",view.pending]].map(([label,count])=><div key={label}><strong>{count}</strong><small>{label}</small></div>)}</div><div className="action-list"><button onClick={()=>go(`/storage/${view.firstDirection}?status=review`)}><span><strong>미확정 거래 {view.unconfirmed}건</strong><small>OCR 결과와 거래 정보를 확인해요</small></span><span>›</span></button><button onClick={()=>go("/storage/purchase?status=review")}><span><strong>공제 분석 확인 {view.pending}건</strong><small>분석 전·판단 보류 거래를 확인해요</small></span><span>›</span></button></div></section> : <p className="banner banner--info">사업자정보를 입력하면 신고기간별 검토 건수가 표시됩니다.</p>}
    {view.period && <section className="card review-checklist"><h2 className="section-title">신고 전 체크리스트</h2><p>{estimate ? "✓" : "○"} 사업자정보·과세유형 확인</p><p>{!view.loading && view.total>0 && view.unconfirmed===0?"✓":"○"} 매입·매출 거래 확정</p><p>{!view.loading && view.total>0 && view.pending===0?"✓":"○"} 공제 보류 거래 확인</p><label><input type="checkbox" checked={reviewed} onChange={e=>setReviewed(e.target.checked)}/> 예상세액 및 계산 근거 검토</label></section>}
    <button className="btn btn--primary" disabled={pdfBusy || !estimate} onClick={()=>void createReviewPdf()}>{pdfBusy?"PDF 생성 중…":"신고 지원용 PDF 생성"}</button>{pdfMessage && <p role="status">{pdfMessage}</p>}
    <p className="footnote">이 자료는 세무 신고서가 아닙니다. 실제 제출 전 내용을 검토해 주세요.</p>
  </main></div>;
}
