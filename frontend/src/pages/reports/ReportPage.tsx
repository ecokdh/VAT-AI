import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { isAxiosError } from "axios";
import { createVatReturnJob, downloadPdfJob, getAsyncJob, getFilingInput, saveFilingInput, type AsyncJobApi, type VatReturnResult } from "../../api/transactions";
import { PageHeader } from "../../components/PageHeader";
import { useReviewOverview, periodLabel, periodOptions } from "../../hooks/useReviewOverview";
import { useMaskedFormat } from "../../hooks/useMaskedFormat";

const isFinalPeriod = (period: string) => /^\d{4}-H[12]$/.test(period);

// 신고서 (24) 예정고지세액. 확정 신고기간에만 입력하고, 신고서 (30) 납부할 세액에서 뺀다.
// 기간이 바뀌면 key로 새로 그려서 이전 기간 값이 남지 않게 한다.
function PreliminaryNoticeTaxField({ period }: { period: string }) {
  const [value, setValue] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    getFilingInput(period).then(r => { if (active) setValue(r.preliminary_notice_tax == null ? "" : r.preliminary_notice_tax.toLocaleString("ko-KR")); })
      .catch(() => { if (active) setMessage("저장된 예정고지세액을 불러오지 못했습니다."); });
    return () => { active = false; };
  }, [period]);
  async function save() {
    const digits = value.replace(/\D/g, "");
    setBusy(true); setMessage("");
    try { await saveFilingInput(period, digits ? Number(digits) : null); setMessage(digits ? "예정고지세액을 저장했습니다." : "예정고지세액을 비웠습니다."); }
    catch { setMessage("예정고지세액을 저장하지 못했습니다. 다시 시도해 주세요."); }
    finally { setBusy(false); }
  }
  return <section className="card preliminary-notice-tax">
    <label className="form-field"><span className="form-field__label">(24) 예정고지세액</span>
      <div className="form-field__input-row"><input className="input" inputMode="numeric" placeholder="예: 1,200,000" value={value} disabled={busy}
        onChange={e => { const digits = e.target.value.replace(/\D/g, ""); setValue(digits ? Number(digits).toLocaleString("ko-KR") : ""); }} />
        <button type="button" className="btn btn--secondary btn--sm" disabled={busy} onClick={() => void save()}>{busy ? "저장 중" : "저장"}</button></div></label>
    <p className="footnote">{message || "4월(1기)·10월(2기)에 국세청 고지서로 미리 낸 세액입니다. 없으면 비워 두세요. 신고서의 납부할 세액에서 빠집니다."}</p>
  </section>;
}

export function ReportPage() {
  const view=useReviewOverview();
  const {period,estimate}=view;
  const navigate=useNavigate();
  const go = (path: string) => navigate(`${path}${path.includes("?") ? "&" : "?"}period=${period}&from=reports`);
  const fmt=useMaskedFormat();
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
      setPdfMessage("부가세 신고서 PDF를 다운로드했습니다.");
    } catch (cause) {
      const message = isAxiosError(cause) ? cause.response?.data?.error?.message : undefined;
      setError(message ?? (cause instanceof Error ? cause.message : "신고서 생성에 실패했습니다."));
      setPdfMessage("");
    } finally { setReturnBusy(false); }
  }

  return <div className="page qa-page"><PageHeader title="신고서 생성" showAmountToggle/><main className="page__body">
    <p className="eyebrow muted">부가가치세 신고 준비</p><h1 className="screen-title">신고할 내용을 확인하세요</h1><p className="muted">확정 거래와 공제 분석을 바탕으로 신고 전 확인사항을 정리했어요.</p>
    <label className="form-field"><span className="form-field__label">신고 대상 기간</span><select className="input" value={period} onChange={e=>{view.setPeriod(e.target.value);setReviewed(false);}}>{periodOptions(view.user?.business?.tax_type_code==="02").map(p=><option key={p} value={p}>{periodLabel(p)}</option>)}</select></label>
    {(error || view.error) && <p className="banner banner--error" role="alert">{error || view.error}</p>}
    {view.loading && <p role="status">신고 준비 상태를 불러오는 중입니다.</p>}
    <section className="report-total"><small className="muted">예상 납부세액</small><strong>{estimate?.payable_estimate==null?"확인 필요":fmt.won(estimate.payable_estimate)}</strong><p className="muted">확정 거래 기준 · 검토를 위한 참고용 추정치</p></section>
    {estimate ? <details className="card"><summary>계산 내역 자세히 보기</summary>{[["매출세액",estimate.output_vat],["일반 매입 공제액",estimate.eligible_input_vat],["의제매입 공제액",estimate.deemed_input_vat]].map(([label,value])=><div className="field-row" key={String(label)}><span>{label}</span><strong>{value==null?"확인 필요":fmt.won(Number(value))}</strong></div>)}{estimate.notes.map(note=><p className="muted" key={note}>{note}</p>)}</details> : <button className="banner banner--warning" onClick={()=>navigate("/account")}>사업자 과세유형 및 설정을 확인해 주세요 ›</button>}
    {isFinalPeriod(period) && <PreliminaryNoticeTaxField key={period} period={period} />}
    <section className="card overview-card"><h2 className="section-title">신고 준비 현황</h2><div className="stat-grid">{[["공제",view.readiness?.deductible??0],["불공제",view.readiness?.nondeductible??0],["확인 필요",view.unconfirmed+view.pending]].map(([label,count])=><div key={label}><strong>{count}</strong><small>{label}</small></div>)}</div><div className="action-list"><button onClick={()=>go(`/storage/${view.firstDirection}?status=review`)}><span><strong>미확정 거래 {view.unconfirmed}건</strong><small>OCR 결과와 거래 정보를 확인해요</small></span><span>›</span></button><button onClick={()=>go("/storage/purchase?status=review")}><span><strong>확인 필요 {view.pending}건</strong><small>분석 전·판단 보류 거래를 확인해요</small></span><span>›</span></button></div></section>
    <section className="card review-checklist"><h2 className="section-title">신고 전 체크리스트</h2>
      {([["business","사업자정보·과세유형 확인","/account"],["transactions","매입·매출 거래 확정",`/storage/${view.firstDirection}?status=review`],["deductions","공제·불공제 판단 확인","/storage/purchase?status=review"],["estimate","예상세액 계산 완료",null]] as const).map(([key,label,path])=><div className="checklist-row" key={key}><span className={view.readiness?.checks[key]?"status-label--done":"muted"}>{view.readiness?.checks[key]?"✓":"○"} {label}</span>{!view.readiness?.checks[key]&&path&&<button className="text-link" onClick={()=>go(path)}>확인하기</button>}</div>)}
      <label className="check-row"><input type="checkbox" checked={reviewed} disabled={view.loading} onChange={e=>setReviewed(e.target.checked)}/>예상세액 및 계산 근거를 검토했습니다.</label>
      {!canGenerate&&<p className="footnote">검토 확인에 체크하면 PDF 생성 버튼이 활성화됩니다.</p>}
    </section>
    <button className="btn btn--primary" disabled={returnBusy || !canGenerate} onClick={()=>void createVatReturn()}>{returnBusy?"신고서 만드는 중…":"부가세 신고서 PDF 생성"}</button>{pdfMessage && <p role="status">{pdfMessage}</p>}
    {returnResult && <section className="card vat-return-result" role="status">
      <h2 className="section-title">신고서 확인 사항</h2>
      <p className={`banner ${returnResult.verification.status === "mismatch" ? "banner--warning" : "banner--info"}`}>{returnResult.verification.message}</p>
      {returnResult.verification.mismatches?.map(m => <div className="field-row" key={m.field}><span>{m.label}</span><span>넣은 값 {m.expected || "(빈칸)"} · 읽은 값 {m.read || "(빈칸)"}</span></div>)}
      <ul>{returnResult.notes.map(note => <li key={note} className="muted">{note}</li>)}</ul>
    </section>}
    <p className="footnote">신고서 PDF는 신고 준비용이며 홈택스에 제출되지 않습니다. 실제 제출 전 내용을 검토해 주세요.</p>
  </main></div>;
}
