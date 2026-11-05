import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { apiClient } from "../api/client";
import { PageHeader } from "./PageHeader";
import { ReceiptPreview } from "./ReceiptPreview";
import { ConfirmDialog } from "./ConfirmDialog";
import { useMaskedFormat } from "../hooks/useMaskedFormat";
import { ProcessingTimeline, useStageReveal, type StageStatuses } from "./ProcessingTimeline";
import "../styles/receipt-review.css";

type Value = string | number | null;
type Values = Record<string, Value>;
export type MonthlyDocument = { 사업장: Values; 거래일: string | null; 집계합계: Values; 매출집계_유형별: Values[]; 세무조정_필수항목: Values };
// 세액 계산에 들어가는 결제수단별 매출(서버의 app/sales_monthly/tax_lines.py가 계산).
export type TaxLine = { name: string; evidence_type: string; tax_treatment: string; total_amount: number; supply_amount: number | null; vat_amount: number | null; supply_estimated: boolean };
export type SavedDocument = { id: number; status: string; created_at: string; document: MonthlyDocument; raw_prediction: MonthlyDocument; warnings: string[]; lines: TaxLine[] };
type LinesSummary = { lines: TaxLine[]; output_vat: number; excluded_count: number; month_valid: boolean };
export const linesTotal = (doc: SavedDocument) => doc.lines.reduce((sum, line) => sum + line.total_amount, 0);

const evidenceLabels: Record<string,string> = { card_receipt:"신용카드·간편결제 매출", cash_receipt:"현금영수증 매출", other:"기타 매출" };
const PAYMENTS = ["카드","현금","간편결제","계좌이체","포인트","기타"];
const TAX_TYPES = ["과세","면세","영세율"];
const TOTAL_FIELDS = ["총판매액","총할인액","취소환불액","실매출액","과세공급가액","부가세합계","면세매출액"];
const ADJUST_FIELDS = ["할인액","취소환불액","포인트사용액","현금영수증발행액"];
const PREVIEW_ROWS = 3;
const blankRow = (): Values => ({원문항목:"",결제수단:null,과세구분:null,합계금액:null,공급가액:null,부가세:null});

// 정산서 인식 요청을 기다리는 동안 매입 영수증과 같은 분석 진행 화면을 보여 주고, 끝나면 onDone을 부른다.
export function MonthlyProcessing({ statuses, preview, onDone }: { statuses: StageStatuses; preview: string; onDone: () => void }) {
  const { revealed, ready, progressCap } = useStageReveal(statuses);
  const done = ready && statuses.missing_field_check === "completed";
  useEffect(() => {
    if (!done) return;
    const timer = window.setTimeout(onDone, 700);
    return () => window.clearTimeout(timer);
  }, [done, onDone]);
  return <div className="page processing-page"><div className="page__body">
    <div className="processing-intro">
      <div className="processing-eyebrow">증빙 분석</div>
      {!done && <div className="ocr-loading-spinner" aria-label="분석 진행 중" />}
      <h1>{done ? "증빙 분석이 끝났어요" : "증빙 분석 중"}</h1>
      <p className="muted">{done ? "원본 사진과 비교해 추출 결과를 확인해 주세요." : "월간 매출 정산서의 합계와 결제수단별 금액을 읽고 있어요."}</p>
    </div>
    <figure className="receipt-preview receipt-preview--wide" aria-label="업로드한 증빙 미리보기">{preview && <img src={preview} alt="업로드한 증빙 원본" />}</figure>
    <ProcessingTimeline statuses={statuses} revealed={revealed} progress={Math.min(done ? 100 : statuses.text_recognition === "processing" ? 25 : 100, progressCap)} note={done ? "추출 결과를 확인해 주세요." : "증빙 정보를 분석하고 있어요…"} />
  </div></div>;
}

function TextField({ label, value, onChange, full, type = "text" }: { label: string; value: Value; onChange: (v: Value) => void; full?: boolean; type?: string }) {
  return <label className={`review-field${full ? " review-full" : ""}`}><span>{label}</span><input className="input" type={type} value={value ?? ""} placeholder="미확인" onChange={e => onChange(e.target.value || null)} /></label>;
}
function MoneyField({ label, value, onChange, full }: { label: string; value: Value; onChange: (v: Value) => void; full?: boolean }) {
  return <label className={`review-field${full ? " review-full" : ""}`}><span>{label} (원)</span><input className="input" type="number" step="1" inputMode="numeric" value={value ?? ""} placeholder="미확인" onChange={e => onChange(e.target.value === "" ? null : Number(e.target.value))} /></label>;
}
function ChoiceField({ label, value, options, onChange }: { label: string; value: Value; options: string[]; onChange: (v: Value) => void }) {
  return <label className="review-field"><span>{label}</span><select className="input" aria-label={label} value={value ?? ""} onChange={e => onChange(e.target.value || null)}><option value="">확인 필요</option>{options.map(o => <option key={o}>{o}</option>)}</select></label>;
}

export function MonthlySalesReviewPage() {
  const { id } = useParams(); const navigate = useNavigate(); const fmt = useMaskedFormat();
  const [search, setSearch] = useSearchParams(); const detailed = search.get("view") === "all";
  const [doc, setDoc] = useState<MonthlyDocument | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [summary, setSummary] = useState<LinesSummary | null>(null);
  const [showAllRows, setShowAllRows] = useState(false);
  const [confirm, setConfirm] = useState<"leave" | "save" | null>(null);
  const [loading, setLoading] = useState(true); const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false); const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    apiClient.get<SavedDocument>(`/sales/monthly/${id}`).then(({ data }) => { if (active) { setDoc(data.document); setWarnings(data.warnings); } })
      .catch(() => { if (active) setError("정산서를 불러오지 못했습니다."); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [id]);
  // 수정할 때마다 세액 계산 반영 결과를 서버 규칙으로 다시 계산한다(저장하지 않음).
  useEffect(() => {
    if (!doc) return;
    let active = true;
    const timer = window.setTimeout(() => apiClient.post<LinesSummary>("/sales/monthly/lines", { document: doc }).then(({ data }) => { if (active) setSummary(data); }).catch(() => {}), 300);
    return () => { active = false; window.clearTimeout(timer); };
  }, [doc]);
  useEffect(() => { const warn = (e: BeforeUnloadEvent) => { if (dirty) { e.preventDefault(); e.returnValue = ""; } }; window.addEventListener("beforeunload", warn); return () => window.removeEventListener("beforeunload", warn); }, [dirty]);

  function edit(change: (draft: MonthlyDocument) => void) {
    setDoc(current => { if (!current) return current; const draft = structuredClone(current); change(draft); return draft; });
    setDirty(true);
  }
  const setIn = (section: "사업장" | "집계합계" | "세무조정_필수항목", name: string) => (v: Value) => edit(d => { d[section][name] = v; });
  const setRow = (index: number, name: string) => (v: Value) => edit(d => { d.매출집계_유형별[index][name] = v; });

  function askSave(e: FormEvent) { e.preventDefault(); if (doc && !saving) setConfirm("save"); }
  async function save() {
    setConfirm(null); if (!doc || saving) return;
    setSaving(true); setError("");
    try { await apiClient.put(`/sales/monthly/${id}/review`, { document: doc }); setDirty(false); navigate("/storage/sales", { replace: true }); }
    catch { setError("수정 내용을 저장하지 못했습니다. 입력값은 유지됩니다."); }
    finally { setSaving(false); }
  }
  function leave() { setDirty(false); navigate("/storage/sales"); }
  function retake() { if (!dirty || window.confirm("수정한 내용이 아직 저장되지 않았습니다. 다시 촬영할까요?")) navigate("/capture?direction=sales"); }

  const rows = doc?.매출집계_유형별 ?? [];
  const groups = Object.entries((summary?.lines ?? []).reduce<Record<string, number>>((sum, l) => ({ ...sum, [l.evidence_type]: (sum[l.evidence_type] ?? 0) + l.total_amount }), {}));

  return <div className="page receipt-review-page">
    <PageHeader title={detailed ? "전체 정보 확인" : "추출 결과 확인"} onBack={() => setConfirm("leave")} />
    <div className="page__body review-body">
      {loading ? <p role="status">결과를 불러오는 중입니다.</p> : doc ? <div className="review-layout">
        <aside className="review-photo"><ReceiptPreview id={Number(id)} monthly controls /></aside>
        <form className="review-form" onSubmit={askSave}>
          {error && <div className="review-error" role="alert">{error}</div>}
          <fieldset disabled={saving}>
            {!detailed && <>
              <section className="review-section"><h2>정산서 정보</h2><div className="review-grid">
                <TextField label="상호" value={doc.사업장.상호} onChange={setIn("사업장", "상호")} full />
                <TextField label="사업자등록번호" value={doc.사업장.사업자등록번호} onChange={setIn("사업장", "사업자등록번호")} full />
                <TextField label="거래월" type="month" value={doc.거래일} onChange={v => edit(d => { d.거래일 = v == null ? null : String(v); })} full />
                <MoneyField label="실매출액" value={doc.집계합계.실매출액} onChange={setIn("집계합계", "실매출액")} full />
                {warnings.map(w => <small className="review-full" key={w}>{w}</small>)}
                <div className="review-field review-full"><span>결제수단별 매출</span><div className="basic-item-names">
                  {rows.slice(0, showAllRows ? rows.length : PREVIEW_ROWS).map((row, i) => <div key={i}>
                    <label className="basic-item-name"><span>{i + 1}</span><input aria-label={`결제수단 ${i + 1} 원문 항목`} className="input" value={row.원문항목 ?? ""} placeholder="정산서에 인쇄된 항목명" onChange={e => setRow(i, "원문항목")(e.target.value)} /></label>
                    <div className="review-item-numbers basic-item-numbers">
                      <ChoiceField label="결제수단" value={row.결제수단} options={PAYMENTS} onChange={setRow(i, "결제수단")} />
                      <ChoiceField label="과세구분" value={row.과세구분} options={TAX_TYPES} onChange={setRow(i, "과세구분")} />
                      <MoneyField label="합계금액" value={row.합계금액} onChange={setRow(i, "합계금액")} />
                    </div></div>)}
                </div>
                  {rows.length === 0 && <p className="muted">읽은 결제수단별 매출이 없습니다. 전체 정보에서 추가할 수 있습니다.</p>}
                  {rows.length > PREVIEW_ROWS && <button type="button" className="text-link" onClick={() => setShowAllRows(v => !v)}>{showAllRows ? "결제수단 접기" : `나머지 ${rows.length - PREVIEW_ROWS}개 결제수단 수정`}</button>}
                </div>
              </div><button type="button" className="btn btn--secondary review-all-button" onClick={() => setSearch({ view: "all" })}>전체 정보 확인</button></section>
              <section className="review-section"><h2>세액 계산 반영</h2>
                {summary && !summary.month_valid && <p className="review-error">거래월을 입력해야 신고 기간의 매출세액에 반영됩니다.</p>}
                {groups.map(([type, total]) => <div className="field-row" key={type}><span className="field-row__label">{evidenceLabels[type]}</span><span className="field-row__value">{fmt.won(total)}</span></div>)}
                {summary && <div className="field-row"><span className="field-row__label">예상 매출세액</span><strong className="field-row__value">{fmt.won(summary.output_vat)}</strong></div>}
                {!!summary?.excluded_count && <p className="muted">과세구분이 비어 있는 {summary.excluded_count}개 결제수단은 계산에서 빠집니다.</p>}
                {summary?.lines.some(l => l.supply_estimated) && <p className="muted">공급가액이 인쇄되지 않은 과세 매출은 합계금액 × 100/110으로 계산했습니다.</p>}
                {summary && !summary.lines.length && <p className="muted">합계금액이 있는 결제수단이 없어 반영할 매출이 없습니다.</p>}
                <p className="muted">저장하면 이 금액이 매출세액과 신고서에 들어갑니다.</p>
              </section>
            </>}
            {detailed && <><button type="button" className="text-link" onClick={() => setSearch({})}>← 기본 정보로 돌아가기</button>
              <section className="review-section"><h2>사업장 · 기간</h2><div className="review-grid">
                <TextField label="상호" value={doc.사업장.상호} onChange={setIn("사업장", "상호")} full />
                <TextField label="사업자등록번호" value={doc.사업장.사업자등록번호} onChange={setIn("사업장", "사업자등록번호")} />
                <TextField label="거래월" type="month" value={doc.거래일} onChange={v => edit(d => { d.거래일 = v == null ? null : String(v); })} />
              </div></section>
              <section className="review-section"><h2>매출 합계</h2><div className="review-grid">{TOTAL_FIELDS.map(name => <MoneyField key={name} label={name} value={doc.집계합계[name]} onChange={setIn("집계합계", name)} />)}</div>
                {warnings.map(w => <p className="muted" key={w}>{w}</p>)}</section>
              <section className="review-section"><div className="review-section-heading"><h2>결제수단별 매출</h2><button type="button" className="review-add" onClick={() => edit(d => { d.매출집계_유형별.push(blankRow()); })}>+ 결제수단 추가</button></div>
                {rows.length === 0 && <p className="review-empty">필요한 결제수단을 추가할 수 있습니다.</p>}
                {rows.map((row, i) => <div className="review-item" key={i}>
                  <div className="review-item-heading"><span>{i + 1}</span><button type="button" aria-label={`${i + 1}번째 결제수단 삭제`} onClick={() => edit(d => { d.매출집계_유형별.splice(i, 1); })}>삭제</button></div>
                  <TextField label="원문 항목" value={row.원문항목} onChange={setRow(i, "원문항목")} />
                  <div className="review-grid">
                    <ChoiceField label="결제수단" value={row.결제수단} options={PAYMENTS} onChange={setRow(i, "결제수단")} />
                    <ChoiceField label="과세구분" value={row.과세구분} options={TAX_TYPES} onChange={setRow(i, "과세구분")} />
                    <MoneyField label="합계금액" value={row.합계금액} onChange={setRow(i, "합계금액")} full />
                    <MoneyField label="공급가액" value={row.공급가액} onChange={setRow(i, "공급가액")} />
                    <MoneyField label="부가세" value={row.부가세} onChange={setRow(i, "부가세")} />
                  </div></div>)}
              </section>
              <section className="review-section"><h2>조정 항목</h2><div className="review-grid">{ADJUST_FIELDS.map(name => <MoneyField key={name} label={name} value={doc.세무조정_필수항목[name]} onChange={setIn("세무조정_필수항목", name)} />)}</div></section>
            </>}
          </fieldset>
          <div className="review-actions"><button type="submit" className="btn btn--primary" disabled={saving}>{saving ? "저장 중…" : "저장하고 보관함으로"}</button><button type="button" className="review-retake" disabled={saving} onClick={retake}>다시 촬영</button></div>
        </form>
      </div> : <div className="review-error" role="alert">{error}</div>}
    </div>
    <ConfirmDialog open={confirm === "leave"} title="수정한 내용을 저장하지 않습니다" confirmLabel="예" cancelLabel="아니요" confirmClassName="btn--primary" onCancel={() => setConfirm(null)} onConfirm={leave} />
    <ConfirmDialog open={confirm === "save"} title="저장하시겠습니까?" confirmLabel="예" cancelLabel="아니요" confirmClassName="btn--primary" busy={saving} onCancel={() => setConfirm(null)} onConfirm={() => void save()} />
  </div>;
}
