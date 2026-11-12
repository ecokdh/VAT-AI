import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { isAxiosError } from "axios";
import { getMe } from "../api/auth";
import { apiClient } from "../api/client";
import { PageHeader } from "./PageHeader";
import { ReceiptPreview } from "./ReceiptPreview";
import { ConfirmDialog } from "./ConfirmDialog";
import { useMaskedFormat } from "../hooks/useMaskedFormat";
import { SALES_PERIODS, friendlySalesPeriods, parseSalesPeriod, salesPeriodQuery } from "../hooks/salesPeriod";
import { ProcessingTimeline, useStageReveal, type StageStatuses } from "./ProcessingTimeline";
import "../styles/receipt-review.css";

type Value = string | number | null;
type Values = Record<string, Value>;
type SalesEvidence = { 문서유형: string; 기간시작: string | null; 기간종료: string | null; 기준일종류: string | null; 내역: Values[] };
export type MonthlyDocument = { 사업장: Values; 거래일: string | null; 집계합계: Values; 매출집계_유형별: Values[]; 세무조정_필수항목: Values; 매출증빙?: SalesEvidence };
const SALES_EVIDENCE_TYPES = ["홈택스카드", "홈택스현금영수증", "매출세금계산서", "매출계산서", "홈택스판매결제대행", "플랫폼정산", "기타매출장", "확인필요"];
const EVIDENCE_AMOUNTS = new Set(["합계금액", "공급가액", "부가세", "비과세금액", "봉사료", "카드금액", "구매전용카드금액", "기타결제금액", "취소환불액", "수수료", "실입금액"]);
const CARD_SHEET_FIELDS = ["순번", "일자또는월", "자료구분", "건수", "합계금액", "카드금액", "구매전용카드금액", "비과세금액"];
const CASH_SHEET_FIELDS = ["일자또는월", "승인번호", "발급수단", "용도구분", "거래구분", "공급가액", "부가세", "봉사료", "합계금액", "발급결과", "원승인번호", "과세구분"];
const CASH_SUMMARY_FIELDS = ["발행구분", "일자또는월", "건수", "합계금액", "공급가액", "부가세", "봉사료"];
const INVOICE_SHEET_FIELDS = ["작성일", "승인번호", "발급일", "전송일", "공급자사업자번호", "공급받는자사업자번호", "합계금액", "공급가액", "부가세", "전자세금계산서분류", "세금계산서종류", "발급유형", "과세구분"];
const PG_SHEET_LABELS: Record<string, string> = {"순번": "순번", "일자또는월": "승인년월", "건수": "건수", "합계금액": "매출금액", "카드금액": "신용카드", "기타결제금액": "기타결제수단", "업체명": "판매(결제)대행업체 상호"};
const FILING_SOURCE: Record<string, string> = {
  홈택스카드: "hometax_card", 홈택스현금영수증: "hometax_cash_receipt", 매출세금계산서: "hometax_sales_invoice",
  홈택스판매결제대행: "pg", 플랫폼정산: "pg",
};
const CASH_SUMMARY_LABELS: Record<string, string> = {"발행구분": "발행 구역", "일자또는월": "거래년월", "합계금액": "총금액", "부가세": "세액"};
const SALES_FIELD_LABELS: Record<string, string> = {작성일:"작성일자", 발급일:"발급일자", 전송일:"전송일자",
  일자또는월:"거래일 또는 거래월", 공급자사업자번호:"공급자 사업자등록번호", 공급받는자사업자번호:"공급받는 자 사업자등록번호",
  부가세:"세액", 전자세금계산서분류:"세금계산서 분류", 세금계산서종류:"세금계산서 종류"};
const SHEET_NAMES: Record<string, string> = {홈택스카드:"카드 매출", 홈택스현금영수증:"현금영수증 매출",
  매출세금계산서:"매출 전자세금계산서", 홈택스판매결제대행:"판매·결제대행 매출"};

function salesMonth(row: Values) {
  const date = row.작성일 ?? row.일자또는월;
  return typeof date === "string" && /^\d{4}-(0[1-9]|1[0-2])(?:-|$)/.test(date) ? date.slice(0,7) : "";
}
function salesMonthLabel(month: string) {
  return month ? `${month.slice(0,4)}년 ${Number(month.slice(5))}월` : "날짜 확인 필요";
}
function salesRowLabel(row: Values) {
  return [row.작성일, row.업체명 ?? row.발행구분 ?? row.자료구분 ?? row.전자세금계산서분류 ?? row.원문항목,
    typeof row.승인번호 === "string" ? `승인번호 끝 ${row.승인번호.slice(-4)}` : null]
    .filter(Boolean).join(" · ") || "매출 내역";
}
function salesMonthGroups(rows: Values[]) {
  const groups = new Map<string, number[]>();
  rows.forEach((row, index) => {
    const month = salesMonth(row);
    const indices = groups.get(month) ?? [];
    indices.push(index);
    groups.set(month, indices);
  });
  return [...groups].sort(([a], [b]) => (a || "9999").localeCompare(b || "9999"));
}
// 세액 계산에 들어가는 결제수단별 매출(서버의 app/sales_monthly/tax_lines.py가 계산).
export type TaxLine = { name: string; evidence_type: string; tax_treatment: string; total_amount: number; supply_amount: number | null; vat_amount: number | null; supply_estimated: boolean };
export type SavedDocument = { id: number; status: string; created_at: string; document: MonthlyDocument; raw_prediction: MonthlyDocument; warnings: string[]; lines: TaxLine[]; file_type?: "spreadsheet" | "image" };
type LinesSummary = { lines: TaxLine[]; output_vat: number; excluded_count: number; month_valid: boolean };
export const linesTotal = (doc: SavedDocument) => doc.lines.reduce((sum, line) => sum + line.total_amount, 0);

function StoredFields({values}: {values: Values}) {
  return <dl className="stored-sales-fields">{Object.entries(values).map(([key, value]) =>
    <div key={key}><dt>{key}</dt><dd>{value == null ? "미확인" :
      typeof value === "number" ? value.toLocaleString("ko-KR") : value}</dd></div>)}</dl>;
}

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
      <p className="muted">{done ? "원본 사진과 비교해 추출 결과를 확인해 주세요." : "매출 자료의 기간과 금액을 읽고 있어요."}</p>
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
  const [stored, setStored] = useState<SavedDocument | null>(null);
  const [isSpreadsheet, setIsSpreadsheet] = useState(false);
  const period = parseSalesPeriod(search.get("period"));
  const selectedRange = period ? SALES_PERIODS[period] : null;
  const bounds = selectedRange ? [selectedRange.start, selectedRange.end] : null;
  const backToSales = period ? `/storage/sales?${salesPeriodQuery(period)}` : "/storage/sales";
  const [scopeConfirmed, setScopeConfirmed] = useState(false);
  const [editingSheet, setEditingSheet] = useState(false);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [summary, setSummary] = useState<LinesSummary | null>(null);
  const [showAllRows, setShowAllRows] = useState(false);
  const [confirm, setConfirm] = useState<"leave" | "save" | null>(null);
  const [loading, setLoading] = useState(true); const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false); const [error, setError] = useState("");

  useEffect(() => {
    if (!period || search.get("period") !== period) return;
    const next = new URLSearchParams(search);
    next.set("period", SALES_PERIODS[period].url);
    setSearch(next, { replace: true });
  }, [period, search, setSearch]);
  useEffect(() => {
    let active = true;
    apiClient.get<SavedDocument>(`/sales/monthly/${id}`).then(({ data }) => { if (active) { setDoc(data.document); setStored(data); setWarnings(data.warnings); setIsSpreadsheet(data.file_type === "spreadsheet"); } })
      .catch(() => { if (active) setError("정산서를 불러오지 못했습니다."); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [id]);
  // 수정할 때마다 세액 계산 반영 결과를 서버 규칙으로 다시 계산한다(저장하지 않음).
  useEffect(() => {
    if (!doc || doc.매출증빙) return;
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
  const scope = doc?.매출증빙;
  const connectSource = search.get("connect") === "1" && bounds && scope ? FILING_SOURCE[scope.문서유형] : undefined;
  const replacing = !!connectSource && search.get("replace") === "1";
  const needsScope = !!connectSource && isSpreadsheet && (!scope?.기간시작 || !scope.기간종료);
  const needsBusiness = !!connectSource && isSpreadsheet && !doc?.사업장.사업자등록번호;
  const needsConfirmation = needsScope || needsBusiness;
  const wrongScope = !!(connectSource && isSpreadsheet && bounds && scope && (
    (scope.기간시작 && scope.기간시작 !== bounds[0]) || (scope.기간종료 && scope.기간종료 !== bounds[1])
    || scope.내역.some(row => {
      const month = salesMonth(row);
      return !!month && (month < bounds[0].slice(0, 7) || month > bounds[1].slice(0, 7));
    })
  ));

  function askSave(e: FormEvent) { e.preventDefault(); if (doc && !saving) setConfirm("save"); }
  async function save() {
    setConfirm(null); if (!doc || saving) return;
    setSaving(true); setError("");
    try {
      const document = structuredClone(doc);
      const evidence = document.매출증빙;
      const filingPath = `/sales/filings/${period}`;
      let existingIds: number[] = [];
      if (connectSource && evidence && bounds) {
        if (wrongScope || (needsConfirmation && !scopeConfirmed)) return;
        if (needsScope) {
          evidence.기간시작 ??= bounds[0];
          evidence.기간종료 ??= bounds[1];
        }
        if (!evidence.기간시작 || !evidence.기간종료 || !evidence.기준일종류) {
          setError("원본의 조회기간과 날짜 기준을 확인해 주세요.");
          return;
        }
        if (isSpreadsheet) {
          const {business} = await getMe();
          if (!business?.business_number) {
            setError("먼저 내 사업장 정보를 등록한 뒤 매출 자료를 연결해 주세요.");
            return;
          }
          const fileNumber = String(document.사업장.사업자등록번호 ?? "").replace(/\D/g, "");
          if (fileNumber && fileNumber !== business.business_number.replace(/\D/g, "")) {
            setError("엑셀의 사업자등록번호가 등록된 사업장과 다릅니다. 해당 사업장의 엑셀을 다시 올려 주세요.");
            return;
          }
          if (needsBusiness) document.사업장.사업자등록번호 = business.business_number;
          document.사업장.상호 ||= business.business_name;
        }
        const {data} = await apiClient.get<{source_statuses: Record<string, {document_ids: number[]}>}>(filingPath);
        existingIds = data.source_statuses[connectSource]?.document_ids ?? [];
        if (!replacing && existingIds.some(existingId => existingId !== Number(id))) {
          setError("이미 연결된 엑셀이 있습니다. 매출 보관함으로 돌아가 ‘엑셀 교체’를 선택해 주세요.");
          return;
        }
      }
      await apiClient.put(`/sales/monthly/${id}/review`, { document });
      if (connectSource && evidence) {
        await apiClient.put(`${filingPath}/sources/${connectSource}`, {
          status: "확인 완료", document_ids: [Number(id)], query_start: evidence.기간시작,
          query_end: evidence.기간종료, basis: evidence.기준일종류, expected_document_ids: existingIds,
        });
      }
      setDirty(false);
      navigate(backToSales, { replace: true });
    } catch (error) {
      setError(isAxiosError(error) ? friendlySalesPeriods(error.response?.data?.error?.message ?? "자료를 저장하거나 연결하지 못했습니다. 다시 시도해 주세요.") : "자료를 저장하지 못했습니다.");
    }
    finally { setSaving(false); }
  }
  function leave() { setDirty(false); navigate(backToSales); }
  async function downloadSpreadsheet() {
    try {
      const {data} = await apiClient.get<Blob>(`/sales/monthly/${id}/image`, {responseType: "blob"});
      const url = URL.createObjectURL(data);
      const link = document.createElement("a");
      link.href = url;
      link.download = data.type === "application/vnd.ms-excel" ? "매출원본.xls" : "매출원본.xlsx";
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch {setError("원본 엑셀을 내려받지 못했습니다.");}
  }
  function retake() { if (!dirty || window.confirm("수정한 내용이 아직 저장되지 않았습니다. 다시 촬영할까요?")) navigate(`/capture?direction=sales${period ? `&${salesPeriodQuery(period)}` : ""}`); }

  const rows = doc?.매출집계_유형별 ?? [];
  const evidence = doc?.매출증빙;
  const isCashSummary = evidence?.문서유형 === "홈택스현금영수증" && evidence.내역[0]?.범위 === "집계";
  const isInvoiceSheet = isSpreadsheet && evidence?.문서유형 === "매출세금계산서";
  const isPgSheet = isSpreadsheet && evidence?.문서유형 === "홈택스판매결제대행";
  const hasPgSplit = isPgSheet && stored?.raw_prediction.매출증빙?.내역.some(row => row.카드금액 != null || row.기타결제금액 != null);
  const pgFields = Object.keys(PG_SHEET_LABELS).filter(name => hasPgSplit || (name !== "카드금액" && name !== "기타결제금액"));
  const sheetFields = isPgSheet ? [...pgFields, "과세구분", "결제수단"] : isInvoiceSheet ? INVOICE_SHEET_FIELDS : evidence?.문서유형 === "홈택스카드" ? CARD_SHEET_FIELDS : isCashSummary ? CASH_SUMMARY_FIELDS : CASH_SHEET_FIELDS;
  const groups = Object.entries((summary?.lines ?? []).reduce<Record<string, number>>((sum, l) => ({ ...sum, [l.evidence_type]: (sum[l.evidence_type] ?? 0) + l.total_amount }), {}));

  if (isSpreadsheet && stored?.status === "reviewed" && !connectSource && !editingSheet && doc && evidence) {
    const money = (value: Value) => typeof value === "number" ? fmt.won(value) : "미확인";
    return <div className="page receipt-review-page sales-evidence-page">
      <PageHeader title={SHEET_NAMES[evidence.문서유형] ?? "매출 자료"} showAmountToggle onBack={leave} />
      <main className="page__body cash-sales-detail">
        <div className="sales-detail-business">
          <strong>{doc.사업장.상호 || "상호 미확인"}</strong>
          {doc.사업장.사업자등록번호 && <small>사업자등록번호 {doc.사업장.사업자등록번호}</small>}
        </div>
        <div className="cash-sales-tools">
          <span>{selectedRange && evidence.기간시작 === selectedRange.start && evidence.기간종료 === selectedRange.end
            ? selectedRange.label : evidence.기간시작 && evidence.기간종료 ? `${evidence.기간시작} ~ ${evidence.기간종료}` : "조회기간 미확인"}</span>
          <button type="button" className="text-link" onClick={() => void downloadSpreadsheet()}>원본 엑셀 내려받기</button>
        </div>
        {error && <p role="alert" className="review-error">{error}</p>}
        <h1 className="section-title">월별 매출</h1>
        <div className="cash-sales-columns" aria-hidden="true"><span>거래월</span><span>건수</span><span>총금액</span></div>
        {salesMonthGroups(evidence.내역).map(([month, indices]) => {
          const entries = indices.map(index => evidence.내역[index]);
          const total = entries.every(row => typeof row.합계금액 === "number")
            ? entries.reduce((sum, row) => sum + Number(row.합계금액), 0) : null;
          const count = isInvoiceSheet ? entries.length : entries.every(row => typeof row.건수 === "number")
            ? entries.reduce((sum, row) => sum + Number(row.건수), 0) : null;
          return <details className="cash-sales-row" key={month}>
            <summary className="cash-sales-columns"><span>{salesMonthLabel(month)}</span>
              <span>{count == null ? "미확인" : `${count.toLocaleString("ko-KR")}건`}</span><span>{money(total)}</span></summary>
            {entries.map((row, index) => <div className="cash-sales-breakdown" key={index}>
              {entries.length > 1 && <strong>{salesRowLabel(row)}</strong>}
              <StoredFields values={Object.fromEntries(sheetFields.map(name => [
                (isPgSheet ? PG_SHEET_LABELS[name] : isCashSummary ? CASH_SUMMARY_LABELS[name] : undefined) ?? SALES_FIELD_LABELS[name] ?? name,
                EVIDENCE_AMOUNTS.has(name) ? money(row[name]) : row[name],
              ]))} />
            </div>)}
          </details>;
        })}
        <div className="vault-actions">
          <button type="button" className="btn btn--secondary" onClick={() => setEditingSheet(true)}>자료 수정</button>
        </div>
      </main>
    </div>;
  }
  if (doc && evidence && evidence.문서유형 !== "POS정산") return <div className="page receipt-review-page sales-evidence-page">
    <PageHeader title={isSpreadsheet ? `${SHEET_NAMES[evidence.문서유형] ?? "매출 자료"} 수정` : "매출 증빙 확인"} onBack={() => { if (!dirty || window.confirm("저장하지 않은 변경사항이 있습니다. 나갈까요?")) leave(); }} />
    <main className={`page__body review-body${isSpreadsheet ? "" : " review-layout"}`}>
      {!isSpreadsheet && <aside className="review-photo"><ReceiptPreview id={Number(id)} monthly controls /></aside>}
      <form className="review-form" onSubmit={e => {e.preventDefault(); void save();}}>
        {error && <p className="review-error" role="alert">{error}</p>}
        {!isSpreadsheet && <section className="review-section">
          <h2>사업장과 조회 범위</h2>
          <div className="review-grid">
            <TextField label="상호" value={doc.사업장.상호} onChange={setIn("사업장", "상호")} />
            <TextField label="사업자등록번호" value={doc.사업장.사업자등록번호} onChange={setIn("사업장", "사업자등록번호")} />
            <ChoiceField label="문서 유형" value={evidence.문서유형} options={SALES_EVIDENCE_TYPES} onChange={v => edit(d => {d.매출증빙!.문서유형 = String(v ?? "확인필요");})} />
            {(["기간시작", "기간종료", "기준일종류"] as const).map(name =>
              <TextField key={name} label={name === "기간시작" ? "조회 시작일" : name === "기간종료" ? "조회 종료일" : "날짜 기준"}
                type={name === "기준일종류" ? "text" : "date"} value={evidence[name]}
                onChange={v => edit(d => {d.매출증빙![name] = v == null ? null : String(v);})} />)}
          </div>
        </section>}
        {wrongScope && <p role="alert">조회기간 또는 매출 날짜가 {selectedRange?.label}과 다릅니다. 해당 기간의 엑셀을 다시 올려 주세요.</p>}
        <section className="review-section">
          <div className="review-section-heading">
            <h2>월별 매출 내역</h2>
            {isSpreadsheet && <button type="button" className="text-link" onClick={() => void downloadSpreadsheet()}>원본 엑셀</button>}
          </div>
          {isSpreadsheet && <p className="muted">수정할 내역을 펼쳐 값을 바꾸고 저장하세요. 원본 엑셀은 그대로 보관됩니다.</p>}
          {!evidence.내역.length && <p>추출된 내역이 없습니다. 원본을 확인해 주세요.</p>}
          {salesMonthGroups(stored?.document.매출증빙?.내역 ?? evidence.내역).map(([month, indices]) => <details className="sales-edit-month" key={month}>
            <summary>{month ? `${Number(month.slice(5))}월` : "날짜 확인 필요"}</summary>
            {indices.map(index => {
              const row = evidence.내역[index];
              const fields = <div className="review-grid" key={index}>{(isSpreadsheet ? sheetFields.map(name => [name, row[name]] as const) : Object.entries(row)).map(([name, value]) => {
              const onChange = (v: Value) => edit(d => {d.매출증빙!.내역[index][name] = v;});
              const label = (isPgSheet ? PG_SHEET_LABELS[name] : isCashSummary ? CASH_SUMMARY_LABELS[name] : undefined) ?? SALES_FIELD_LABELS[name] ?? name;
              if (isPgSheet && name === "결제수단") return <ChoiceField key={name} label="누락분 결제 구분" value={value} options={["카드", "증빙 미발급 기타 결제"]} onChange={onChange} />;
              if (name === "범위") return <ChoiceField key={name} label={name} value={value} options={["건별", "집계", "합계"]} onChange={onChange} />;
              if (name === "과세구분" && isSpreadsheet) return <ChoiceField key={name} label={name} value={value} options={TAX_TYPES} onChange={onChange} />;
              if (name === "건수" || name === "순번") return <label key={name} className="review-field">{label}<input className="input" type="number" min={name === "순번" ? 1 : 0} step="1" value={value ?? ""} onChange={e => onChange(e.target.value === "" ? null : Number(e.target.value))} /></label>;
              return EVIDENCE_AMOUNTS.has(name) ? <MoneyField key={name} label={label} value={value} onChange={onChange} />
                : <TextField key={name} label={label} value={value} type={["작성일","발급일","전송일"].includes(name) ? "date"
                  : name === "일자또는월" && isSpreadsheet && row.범위 === "집계" ? "month" : "text"} onChange={onChange} />;
              })}</div>;
              return indices.length === 1 ? fields : <details className="sales-edit-entry" key={index}>
                <summary>{salesRowLabel(row)}{typeof row.합계금액 === "number" ? ` · ${fmt.won(row.합계금액)}` : ""}</summary>
                {fields}
              </details>;
            })}
          </details>)}
        </section>
        {needsConfirmation && !wrongScope && selectedRange && <label className="check-row">
          <input type="checkbox" checked={scopeConfirmed} onChange={event => setScopeConfirmed(event.target.checked)} />
          등록된 사업장의 {selectedRange.label} 전체 자료입니다.
        </label>}
        {replacing && <p className="muted">교체하면 이 기간에 새 엑셀이 연결됩니다. 이전 파일은 보관함에서 볼 수 있습니다.</p>}
        <button className="btn btn--primary" disabled={saving || wrongScope || (needsConfirmation && !scopeConfirmed) || evidence.문서유형 === "확인필요" || !evidence.내역.length}>{saving ? "저장 중" : replacing ? "새 엑셀로 교체" : connectSource ? "확인하고 신고자료에 연결" : "수정 내용 저장"}</button>
      </form>
    </main>
  </div>;

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
                <p className="muted">저장한 증빙은 매출 보관함에서 확인할 수 있습니다. 신고서는 해당 기간의 확정 매출을 사용합니다.</p>
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
