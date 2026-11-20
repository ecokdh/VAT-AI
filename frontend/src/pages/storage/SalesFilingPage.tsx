import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { isAxiosError } from "axios";
import { Link, useSearchParams } from "react-router-dom";
import { apiClient } from "../../api/client";
import { getMe } from "../../api/auth";
import { PageHeader } from "../../components/PageHeader";
import { VaultTabs } from "../../components/VaultTabs";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import type { SavedDocument } from "../../components/MonthlySalesReview";
import { SalesDuplicateCheckPanel, type FilingIssue } from "../../components/SalesDuplicateCheckPanel";
import { formatWon } from "../../utils/format";
import { SALES_PERIODS, friendlySalesPeriods, parseSalesPeriod, salesPeriodQuery, salesPeriods, type SalesPeriod } from "../../hooks/salesPeriod";
import { rememberPeriod, rememberedPeriod, useReturnedPeriod } from "../../hooks/currentPeriod";
import "../../styles/sales-filing.css";

const sources = [
  ["hometax_card", "홈택스 카드", ["홈택스카드"], "승인월"],
  ["hometax_cash_receipt", "홈택스 현금영수증", ["홈택스현금영수증"], "거래년월"],
  ["hometax_sales_invoice", "매출 세금계산서", ["매출세금계산서"], "작성일"],
  ["pg", "판매·결제대행", ["홈택스판매결제대행", "플랫폼정산"], "정산기간"],
] as const;
const spreadsheetLabels = {
  card: "월별 카드 매출 엑셀",
  cash: "현금영수증 매출내역누계 엑셀",
  invoice: "반기별 매출 전자세금계산서 목록 엑셀",
  pg: "홈택스 판매·결제대행 엑셀",
};
const statuses = ["자료 없음", "검토 필요", "확인 완료", "해당 없음 확인"] as const;
type Source = typeof sources[number];
type Check = {status: typeof statuses[number]; query_start?: string; query_end?: string; basis?: string; reason?: string; document_ids: number[]};
type Filing = {
  period: string; status: string; revision: number; reconfirmation_required: boolean;
  source_statuses: Record<string, Check>;
  other_sales?: OtherSale[];
  other_sales_total?: OtherSalesTotal | null;
  issues: FilingIssue[];
  aggregate: {
    lines?: Record<string, {supply_amount: number; vat_amount: number; total_amount?: number}>;
    included_rows?: IncludedSalesRow[];
  };
};
type IncludedSalesRow = {source: string; document_id: number | null; date?: string | null; scope?: string; supply_amount: number; total_amount: number};
type OtherSalesTotal = {total_amount: number; supporting_evidence?: string};
type OtherSale = {
  input_key: string; date: string | null; description: string; payment_method: string;
  supply_amount: number | null; total_amount: number | null;
};
type Submit = (path: string, body?: object, method?: "post" | "put") => Promise<boolean>;
const resolvedSourceStatuses = new Set(["확인 완료", "해당 없음 확인"]);

function monthsInPeriod(period: SalesPeriod) {
  const [startYear, startMonth] = SALES_PERIODS[period].start.slice(0, 7).split("-").map(Number);
  const [endYear, endMonth] = SALES_PERIODS[period].end.slice(0, 7).split("-").map(Number);
  const months: string[] = [];
  let year = startYear;
  let month = startMonth;
  while (year < endYear || (year === endYear && month <= endMonth)) {
    months.push(String(year) + "-" + String(month).padStart(2, "0"));
    month += 1;
    if (month > 12) { year += 1; month = 1; }
  }
  return months;
}

function monthForRowDate(value?: string | null) {
  if (!value || value.length < 7 || value[4] !== "-") return null;
  const month = Number(value.slice(5, 7));
  return Number.isInteger(month) && month >= 1 && month <= 12 ? value.slice(0, 7) : null;
}

const sourceIconPaths = {
  hometax_card: "M3 6h18v12H3z M3 10h18 M6 14h4",
  hometax_cash_receipt: "M5 3h14v18l-3-2-4 2-4-2-3 2z M8 8h8 M8 12h8",
  hometax_sales_invoice: "M5 3h9l5 5v13H5z M14 3v5h5 M8 12h8 M8 16h8",
  pg: "M3 9l2-5h14l2 5 M3 9h18v2a3 3 0 0 1-6 0 3 3 0 0 1-6 0 3 3 0 0 1-6 0z M5 14v6h14v-6",
  other: "M5 3h14v18l-3-2-4 2-4-2-3 2z M8 9h8 M8 13h8",
};

// 출처 칸: 아이콘 | 이름 / (상태 · 버튼들) — 버튼을 상태 줄에 두어 칸 높이를 낮춘다.
function SourceLabel({source, title, status, tone, children}: {source: keyof typeof sourceIconPaths; title: string; status: string; tone?: "ready"; children: ReactNode}) {
  return <div className="sales-source-label">
    <span className="sales-source-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round"><path d={sourceIconPaths[source]} /></svg></span>
    <div className="sales-source-name"><strong>{title}</strong>
      <div className="sales-source-meta"><small className="sales-source-status" data-tone={tone}>{status}</small>{children}</div></div>
  </div>;
}

function OtherSalesCard({revision, sales, total, busy, submit}: {
  revision: number; sales: OtherSale[]; total?: OtherSalesTotal | null; busy: boolean; submit: Submit;
}) {
  const [showList, setShowList] = useState(false);
  const [draft, setDraft] = useState<{amount: string; revision: number} | null>(null);
  const gross = Number(draft?.amount || 0);
  const clearing = !!total && draft?.amount === "0";

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!draft || busy) return;
    const fields = new FormData(event.currentTarget);
    if (await submit("/other-sales", {
      total_amount: gross,
      memo: fields.get("memo"),
      confirmed_unreported: fields.has("confirmed"),
      replace_legacy: fields.has("replace_legacy"),
      expected_revision: draft.revision,
    }, "put")) {
      setDraft(null);
    }
  }

  const status = total ? formatWon(total.total_amount) : sales.length ? `기존 내역 ${sales.length}건` : "입력 내역 없음";
  return <section className="sales-source sales-source--row">
    <div className="sales-source-row">
      <SourceLabel source="other" title="기타 매출" status={status} tone={total || sales.length ? "ready" : undefined}>
        <div className="sales-source-actions">
          {(total || sales.length > 0) && <button type="button" aria-expanded={showList} disabled={busy}
            onClick={() => setShowList(!showList)}>{showList ? "닫기" : "내역 보기"}</button>}
          <button type="button" disabled={busy || !!draft}
            onClick={() => {
              setShowList(false);
              setDraft({amount: total ? String(total.total_amount) : "", revision});
            }}>{total ? "수정" : "내역 입력"}</button>
        </div>
      </SourceLabel>
    </div>
    {(showList || draft) && <div className="sales-source__content">
      {showList && total && <div className="sales-other-sales-values">
        <span>합계 {formatWon(total.total_amount)}</span>
        {total.supporting_evidence && <span className="sales-other-sales-memo">{total.supporting_evidence}</span>}
      </div>}
      {showList && sales.length > 0 && <>
        <strong>{total ? "기존 거래별 내역 (반기 합계로 대체됨)" : "기존 거래별 내역"}</strong>
        {sales.map(sale => <div className="sales-document-card" key={sale.input_key}>
          <span className="sales-document-card__info">
            <strong>{sale.description || sale.payment_method || "기타 매출"}</strong>
            <small>{sale.date || "거래일 미입력"} · {sale.payment_method || "결제수단 미입력"}</small>
            <small>{sale.supply_amount != null ? `공급가액 ${formatWon(sale.supply_amount)}` : `합계 ${formatWon(sale.total_amount ?? 0)}`}</small>
          </span>
        </div>)}
      </>}
      {draft && <form className="sales-other-sales-form" onSubmit={save}>
        <div className="sales-other-sales-values">
          <label>합계 (부가세 포함)
            <input className="input" type="number" min={total ? "0" : "1"} max="1099999999998" step="1"
              value={draft.amount} onChange={event => setDraft({...draft, amount: event.target.value})} required />
          </label>
          <label>메모 (선택)
            <input className="input" name="memo" maxLength={2000} defaultValue={total?.supporting_evidence ?? ""} />
          </label>
        </div>
        {gross > 0 && <label className="sales-other-sales-confirm">
          <input type="checkbox" name="confirmed" required />다른 매출 자료에 포함된 금액은 제외했습니다.
        </label>}
        {gross > 0 && !total && sales.length > 0 && <label className="sales-other-sales-confirm">
          <input type="checkbox" name="replace_legacy" required />기존 거래별 내역을 포함한 반기 합계로 대체합니다.
        </label>}
        {clearing && <small>
          반기 합계를 해제합니다.{sales.length > 0 && " 기존 거래별 내역 기준으로 돌아갑니다."}
        </small>}
        <div className="sales-source-actions">
          <button type="button" disabled={busy} onClick={() => setDraft(null)}>취소</button>
        </div>
        <button type="submit" className="btn btn--secondary" disabled={busy || !draft.amount}>
          {clearing ? "합계 해제" : "저장"}
        </button>
      </form>}
    </div>}
  </section>;
}

function quarterSlotsForPeriod(period: SalesPeriod) {
  return period === "2026-H1"
    ? [
        { key: "q1", label: "1분기 (1~3월)", months: new Set(["2026-01", "2026-02", "2026-03"]) },
        { key: "q2", label: "2분기 (4~6월)", months: new Set(["2026-04", "2026-05", "2026-06"]) },
      ]
    : [
        { key: "q3", label: "3분기 (7~9월)", months: new Set(["2026-07", "2026-08", "2026-09"]) },
        { key: "q4", label: "4분기 (10~12월)", months: new Set(["2026-10", "2026-11", "2026-12"]) },
      ];
}

function docMatchesSlot(doc: SavedDocument, slotMonths: Set<string>) {
  const rows = doc.document.매출증빙?.내역 ?? [];
  const months = rows
    .map(r => String(r.작성일 ?? r.일자또는월 ?? "").slice(0, 7))
    .filter(m => /^\d{4}-\d{2}$/.test(m));
  return months.length > 0 && months.every(m => slotMonths.has(m));
}

function salesDetailPath(period: SalesPeriod, ids: number[]) {
  if (!ids.length) return undefined;
  const documents = ids.length > 1 ? `&docs=${ids.join(",")}` : "";
  return `/receipts/monthly/${ids[0]}/review?${salesPeriodQuery(period)}&edit=1${documents}`;
}

function SourceForm({source, saved, docs, submit, busy, period, onConnected, onDeleted}: {
  source: Source; saved?: Check; docs: SavedDocument[]; submit: Submit; busy: boolean; period: SalesPeriod;
  onConnected: Connected; onDeleted: (ids: number[]) => void;
}) {
  const [openPanel, setOpenPanel] = useState<"replace" | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const linked = saved?.document_ids ?? [];
  const linkedDocs = docs.filter(doc => linked.includes(doc.id));
  const allowsMultiple = source[0] === "hometax_cash_receipt";
  const showQuarterSlots = allowsMultiple && saved?.basis !== "거래년월";
  const status = linked.length ? "업로드 완료" : saved?.status === "해당 없음 확인" ? "자료 없음 확인" : "연결 안 됨";
  const detailPath = salesDetailPath(period, linkedDocs.map(doc => doc.id));
  async function remove() {
    const unlinked = await submit("/sources/" + source[0], {status: "자료 없음", document_ids: []}, "put");
    setConfirmDelete(false);
    if (!unlinked) return;
    await Promise.allSettled(linked.map(id => apiClient.post(`/sales/monthly/${id}/trash`)));
    onDeleted(linked);
  }
  const controls = `sales-source-${source[0]}`;
  const slots = quarterSlotsForPeriod(period);
  return <section className="sales-source sales-source--row">
    <div className="sales-source-row">
      <SourceLabel source={source[0]} title={source[1]} status={status}
        tone={linked.length ? "ready" : undefined}>
      <div className="sales-source-actions">
        {!linked.length && <SpreadsheetUploadButton source={source} period={period} existingIds={[]} mode="replace" onConnected={onConnected} />}
        {detailPath && <Link to={detailPath}>상세 보기</Link>}
        {linked.length > 0 && <button type="button" className="sales-source-replace" aria-expanded={openPanel === "replace"} aria-controls={controls}
          onClick={() => setOpenPanel(value => value === "replace" ? null : "replace")}>
          {openPanel === "replace" ? "닫기" : "엑셀 교체"}
        </button>}
        {linked.length > 0 && <button type="button" className="sales-source-delete" disabled={busy} onClick={() => setConfirmDelete(true)}>삭제</button>}
      </div>
      </SourceLabel>
    </div>
    {openPanel === "replace" && <div className="sales-source__content" id={controls}>
      {showQuarterSlots ? (
        <div className="sales-quarter-slots">
          {slots.map(slot => {
            const slotDoc = linkedDocs.find(d => docMatchesSlot(d, slot.months));
            return (
              <div className="sales-quarter-slot" key={slot.key}>
                <strong className="sales-quarter-slot__title">{slot.label}</strong>
                <SpreadsheetReplace
                  source={source}
                  period={period}
                  existingIds={linked}
                  replaceDocId={slotDoc?.id}
                  targetMonths={slot.months}
                  slotLabel={slot.label}
                  submitLabel="새 엑셀로 교체"
                  onConnected={(filing, doc) => {
                    if (slotDoc && slotDoc.id !== doc.id) {
                      void apiClient.post(`/sales/monthly/${slotDoc.id}/trash`).catch(() => {});
                      onDeleted([slotDoc.id]);
                    }
                    setOpenPanel(null);
                    onConnected(filing, doc);
                  }}
                />
              </div>
            );
          })}
        </div>
      ) : (
        <SpreadsheetReplace source={source} period={period} existingIds={linked}
          onConnected={(filing, doc) => { setOpenPanel(null); onConnected(filing, doc); }} />
      )}
    </div>}
    <ConfirmDialog open={confirmDelete} title={`${source[1]} 자료를 삭제할까요?`} confirmLabel="삭제" busy={busy}
      onCancel={() => setConfirmDelete(false)} onConfirm={() => void remove()}>
      올린 엑셀을 휴지통으로 옮기고 이 출처를 ‘연결 안 됨’으로 되돌립니다. 휴지통에서 복원할 수 있어요.
    </ConfirmDialog>
  </section>;
}

const spreadsheetSources = {
  hometax_card: "card", hometax_cash_receipt: "cash", hometax_sales_invoice: "invoice", pg: "pg",
} as const;

type Connected = (filing: Filing, doc: SavedDocument) => void;

class UploadError extends Error {}

// 엑셀을 올리고 확인 화면 없이 바로 이 신고기간 출처에 연결한다. 연결하지 못하면 올린 자료를 지운다.
async function uploadAndConnect(
  file: File,
  source: Source,
  period: SalesPeriod,
  existingIds: number[],
  mode: "replace" | "append" = "replace",
  existingBasis?: string,
  options?: { replaceDocId?: number; targetMonths?: Set<string>; slotLabel?: string },
) {
  const body = new FormData();
  body.set("file", file);
  body.set("source", spreadsheetSources[source[0]]);
  const {data: uploaded} = await apiClient.post<SavedDocument>("/sales/monthly/spreadsheet", body);
  try {
    const range = SALES_PERIODS[period];
    const document = structuredClone(uploaded.document);
    const evidence = document.매출증빙;
    if (!evidence || !source[2].some(type => type === evidence.문서유형)) throw new UploadError(`${source[1]} 엑셀이 아닙니다. 맞는 엑셀을 올려 주세요.`);
    if (!evidence.기준일종류) throw new UploadError("엑셀의 날짜 기준을 읽지 못했습니다.");
    if (mode === "append" && existingBasis && evidence.기준일종류 !== existingBasis) {
      throw new UploadError(`이미 연결된 자료(${existingBasis})와 형식이 다릅니다. 기존 자료를 삭제하거나 교체한 뒤 올려 주세요.`);
    }
    const months = evidence.내역.map(row => String(row.작성일 ?? row.일자또는월 ?? "").slice(0, 7)).filter(month => /^\d{4}-\d{2}$/.test(month));
    const isDetailCash = source[0] === "hometax_cash_receipt" && evidence.기준일종류 === "거래일";
    const outside = isDetailCash
      ? ((evidence.기간시작 && evidence.기간시작 < range.start) || (evidence.기간종료 && evidence.기간종료 > range.end)
        || months.some(month => month < range.start.slice(0, 7) || month > range.end.slice(0, 7)))
      : ((evidence.기간시작 && evidence.기간시작 !== range.start) || (evidence.기간종료 && evidence.기간종료 !== range.end)
        || months.some(month => month < range.start.slice(0, 7) || month > range.end.slice(0, 7)));
    if (outside) throw new UploadError(`엑셀의 기간이 ${range.label}과 다릅니다. 신고 대상 기간을 바꾼 뒤 다시 올려 주세요.`);
    if (options?.targetMonths && isDetailCash && months.some(month => !options.targetMonths!.has(month))) {
      throw new UploadError(`${options.slotLabel ?? "해당 분기"} 기간에 맞는 엑셀을 올려 주세요.`);
    }
    evidence.기간시작 ??= range.start;
    evidence.기간종료 ??= range.end;
    const {business} = await getMe();
    if (!business?.business_number) throw new UploadError("먼저 내 사업장 정보를 등록한 뒤 매출 자료를 올려 주세요.");
    const fileNumber = String(document.사업장.사업자등록번호 ?? "").replace(/\D/g, "");
    if (fileNumber && fileNumber !== business.business_number.replace(/\D/g, "")) throw new UploadError("엑셀의 사업자등록번호가 등록된 사업장과 다릅니다.");
    document.사업장.사업자등록번호 ||= business.business_number;
    document.사업장.상호 ||= business.business_name;
    const {data: reviewed} = await apiClient.put<SavedDocument>(`/sales/monthly/${uploaded.id}/review`, {document});
    const nextIds = options?.targetMonths && isDetailCash
      ? [...existingIds.filter(id => id !== options.replaceDocId), uploaded.id]
      : mode === "append" ? [...existingIds, uploaded.id] : [uploaded.id];
    const {data: filing} = await apiClient.put<Filing>(`/sales/filings/${period}/sources/${source[0]}`, {
      status: "확인 완료", document_ids: nextIds, query_start: isDetailCash ? range.start : evidence.기간시작,
      query_end: isDetailCash ? range.end : evidence.기간종료, basis: evidence.기준일종류, expected_document_ids: existingIds,
      invoice_replacement_id: source[0] === "hometax_sales_invoice" && mode === "replace" && existingIds.length
        ? crypto.randomUUID() : undefined,
    });
    return {filing, doc: {...uploaded, ...reviewed, document}};
  } catch (e) {
    if (!existingIds.includes(uploaded.id)) {
      await apiClient.post(`/sales/monthly/${uploaded.id}/trash`).then(() => apiClient.delete(`/sales/monthly/${uploaded.id}`)).catch(() => {});
    }
    throw e;
  }
}

const uploadError = (e: unknown) => e instanceof UploadError ? e.message
  : isAxiosError(e) ? friendlySalesPeriods(e.response?.data?.error?.message ?? "엑셀을 올리지 못했습니다.") : "엑셀을 올리지 못했습니다.";

// 아직 자료가 없는 출처 또는 분기 추가 업로드: 파일을 고르면 바로 올려 연결한다.
function SpreadsheetUploadButton({
  source,
  period,
  existingIds = [],
  existingBasis,
  mode = "replace",
  label = "엑셀 업로드",
  className = "sales-source-upload",
  onConnected,
}: {
  source: Source;
  period: SalesPeriod;
  existingIds?: number[];
  existingBasis?: string;
  mode?: "replace" | "append";
  label?: string;
  className?: string;
  onConnected: Connected;
}) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  async function upload(file?: File) {
    if (!file || uploading) return;
    setUploading(true);
    setError("");
    try {
      const {filing, doc} = await uploadAndConnect(file, source, period, existingIds, mode, existingBasis);
      onConnected(filing, doc);
    } catch (e) {
      setError(uploadError(e));
    } finally { setUploading(false); }
  }
  return <>
    <label className={className} aria-disabled={uploading}>
      <input className="sr-only" aria-label={spreadsheetLabels[spreadsheetSources[source[0]]]} type="file" accept=".xls,.xlsx" disabled={uploading}
        onChange={event => { void upload(event.currentTarget.files?.[0]); event.currentTarget.value = ""; }} />
      {uploading ? "올리는 중" : label}
    </label>
    {error && <small className="sales-source-error" role="alert">{error}</small>}
  </>;
}

function SpreadsheetReplace({
  source,
  period,
  existingIds,
  replaceDocId,
  targetMonths,
  slotLabel,
  submitLabel = "새 엑셀로 교체",
  onConnected,
}: {
  source: Source;
  period: SalesPeriod;
  existingIds: number[];
  replaceDocId?: number;
  targetMonths?: Set<string>;
  slotLabel?: string;
  submitLabel?: string;
  onConnected: Connected;
}) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [fileName, setFileName] = useState("");
  async function replace(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (uploading || !fileName) return;
    const file = new FormData(event.currentTarget).get("file");
    if (!(file instanceof File)) return;
    setUploading(true);
    setError("");
    try {
      const {filing, doc} = await uploadAndConnect(file, source, period, existingIds, "replace", undefined, {
        replaceDocId,
        targetMonths,
        slotLabel,
      });
      setFileName("");
      onConnected(filing, doc);
    } catch (e) {
      setError(uploadError(e));
    } finally { setUploading(false); }
  }
  return <form className="sales-form" onSubmit={replace}>
    <label className="sales-file-picker">
      <input className="sr-only" aria-label={slotLabel ? `${slotLabel} ${spreadsheetLabels[spreadsheetSources[source[0]]]}` : spreadsheetLabels[spreadsheetSources[source[0]]]} name="file" type="file" accept=".xls,.xlsx" required
        onChange={event => { setFileName(event.currentTarget.files?.[0]?.name ?? ""); setError(""); }} />
      <span>{fileName ? "다른 파일 선택" : "엑셀 파일 선택"}</span>
    </label>
    {fileName && <p className="muted sales-file-name" role="status">{fileName}</p>}
    <button className="btn btn--secondary" disabled={uploading || !fileName}>{uploading ? "엑셀 읽는 중" : submitLabel}</button>
    {error && <p role="alert">{error}</p>}
  </form>;
}

export function SalesFilingPage() {
  const [search, setSearch] = useSearchParams();
  const requestedPeriod = search.get("period");
  const returnedPeriod = parseSalesPeriod(useReturnedPeriod());
  const selectedPeriod = returnedPeriod ?? parseSalesPeriod(requestedPeriod)
    ?? (!requestedPeriod || requestedPeriod === "all" ? parseSalesPeriod(rememberedPeriod()) ?? "2026-H1" : undefined);
  const period = selectedPeriod ?? "2026-H1";
  const [filing, setFiling] = useState<Filing | null>(null);
  const [docs, setDocs] = useState<SavedDocument[]>([]);
  // edit=1 출처 목록(수정), edit=0 월별 매출. 없으면 자료가 모두 확인됐을 때만 월별 매출을 보여준다.
  const editMode = search.get("edit");
  const editingSources = editMode === "1";
  const setEditingSources = (editing: boolean) => setSearch(previous => {
    const next = new URLSearchParams(previous);
    next.set("edit", editing ? "1" : "0");
    return next;
  }, {replace: true});
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [duplicateChoices, setDuplicateChoices] = useState<Record<string, "O" | "X">>({});
  const path = `/sales/filings/${period}`;
  useEffect(() => {
    if (!selectedPeriod) return;
    rememberPeriod(selectedPeriod);
    if (requestedPeriod === SALES_PERIODS[selectedPeriod].url) return;
    setSearch(previous => {
      const next = new URLSearchParams(previous);
      next.set("period", SALES_PERIODS[selectedPeriod].url);
      return next;
    }, { replace: true });
  }, [selectedPeriod, requestedPeriod, setSearch]);
  useEffect(() => {
    const controller = new AbortController();
    setFiling(null); setBusy(!!selectedPeriod); setError("");
    if (!selectedPeriod) return;
    Promise.all([
      apiClient.get<Filing>(path, {signal: controller.signal}),
      apiClient.get<SavedDocument[]>("/sales/monthly", {signal: controller.signal}),
    ]).then(([result, documents]) => {
      setFiling(result.data); setDocs(documents.data);
    }).catch(e => {if (!controller.signal.aborted) setError(message(e));})
      .finally(() => {if (!controller.signal.aborted) setBusy(false);});
    return () => controller.abort();
  }, [path, selectedPeriod]);

  function message(error: unknown) {
    if (isAxiosError(error)) {
      if (error.response?.status === 401) return "로그인한 뒤 매출 자료를 확인해 주세요.";
      const detail = error.response?.data?.error?.message ?? error.response?.data?.detail;
      if (typeof detail === "string") return friendlySalesPeriods(detail);
    }
    return "매출 자료를 처리하지 못했습니다. 입력값이나 서버 연결을 확인해 주세요.";
  }
  const submit: Submit = async (suffix, body, method = "post") => {
    if (busy) return false;
    setBusy(true); setError("");
    try {
      setFiling((await apiClient.request<Filing>({url: path + suffix, method, data: body})).data);
      return true;
    } catch (e) {setError(message(e)); return false;}
    finally {setBusy(false);}
  };
  const duplicateIssues = (filing?.issues ?? []).filter(issue => issue.reason_code === "POSSIBLE_INVOICE_CARD_DUPLICATE");
  const otherIssues = (filing?.issues ?? []).filter(issue =>
    issue.reason_code !== "POSSIBLE_INVOICE_CARD_DUPLICATE"
    && issue.reason_code !== "SOURCE_MISSING"
    && issue.reason_code !== "CONFIRMED_INPUT_CHANGED",
  );

  async function saveDuplicateChoices(current: Filing, targetIssues: FilingIssue[]) {
    let latest = current;
    for (const issue of targetIssues) {
      const choice = duplicateChoices[issue.issue_id];
      if (!choice) continue;
      const amount = issue.impact_amount ?? issue.details?.counterpart.total_amount ?? 0;
      const shortSource = (issue.details?.counterpart.label ?? "현금영수증·카드").replace("홈택스 ", "");
      const response = await apiClient.post<Filing>(`${path}/feedback`, {
        request_id: `ox-${period}-${issue.issue_id}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        issue_id: issue.issue_id,
        action: choice === "O" ? "중복 확인" : "해당 없음",
        amount,
        evidence: choice === "O"
          ? `사용자 O 선택: 매출 세금계산서와 동일 거래로 ${shortSource}에서 제외`
          : `사용자 X 선택: 별개 거래로 ${shortSource} 및 세금계산서 모두 합산`,
      });
      latest = response.data;
      setFiling(latest);
    }
    setDuplicateChoices(current => {
      const remaining = new Set(latest.issues.map(item => item.issue_id));
      return Object.fromEntries(Object.entries(current).filter(([id]) => remaining.has(id)));
    });
    return latest;
  }

  async function handleSaveDuplicateChoices() {
    if (busy || !filing) return;
    const chosen = duplicateIssues.filter(issue => duplicateChoices[issue.issue_id] != null);
    if (!chosen.length) return;
    setBusy(true); setError("");
    try {
      const updated = await saveDuplicateChoices(filing, chosen);
      if (!updated.issues.some(issue => issue.reason_code === "POSSIBLE_INVOICE_CARD_DUPLICATE")) {
        await finalizeSales(updated);
      }
    } catch (e) {
      setError(message(e));
      const latest = await apiClient.get<Filing>(path).catch(() => null);
      if (latest) setFiling(latest.data);
    } finally {
      setBusy(false);
    }
  }

  async function finalizeSales(current: Filing) {
    if (current.status === "확정") return;
    for (const source of [...sources.map(item => item[0]), "unissued_sales"]) {
      const status = current.source_statuses[source]?.status ?? "자료 없음";
      if (status !== "자료 없음") continue;
      await apiClient.put(`${path}/sources/${source}`, {
        status: "해당 없음 확인", document_ids: [], reason: "사업자가 매출 증빙 확정 시 이 신고기간에 해당 자료가 없음을 확인함.",
      });
    }
    setFiling((await apiClient.post<Filing>(`${path}/finalize`, {confirm_changed_sources: true})).data);
  }

  async function confirmSales() {
    if (busy || !filing) return;
    if (duplicateIssues.length > 0) {
      setError("");
      setEditingSources(false);
      return;
    }
    setBusy(true); setError("");
    try {
      await finalizeSales(filing);
      setEditingSources(false);
    } catch (e) {
      setError(message(e));
      setFiling((await apiClient.get<Filing>(path).catch(() => ({data: filing}))).data);
    } finally {
      setBusy(false);
    }
  }
  const connected: Connected = (next, doc) => {
    setFiling(next);
    setDocs(current => [...current.filter(item => item.id !== doc.id), doc]);
  };
  const line = filing?.aggregate.lines?.["9"];
  const allSourcesComplete = !!filing && sources.every(source => resolvedSourceStatuses.has(filing.source_statuses[source[0]]?.status ?? ""));
  const showSetup = editingSources || (editMode !== "0" && !allSourcesComplete);
  const periodMonths = selectedPeriod ? monthsInPeriod(selectedPeriod) : [];
  const monthTotals = new Map<string, number>(periodMonths.map(month => [month, 0] as [string, number]));
  const includedRows = filing?.aggregate.included_rows ?? [];
  const otherSalesTotal = includedRows.find(row => row.source === "unissued_sales" && row.scope === "period_total");
  includedRows.forEach(row => {
    const month = monthForRowDate(row.date);
    if (month && monthTotals.has(month)) monthTotals.set(month, (monthTotals.get(month) ?? 0) + row.supply_amount);
  });
  const navigationPeriod = selectedPeriod ?? requestedPeriod;
  return <div className="page qa-page sales-filing-page"><PageHeader title="매출 보관함" onBack={editingSources ? () => setEditingSources(false) : undefined} /><main className="page__body sales-filing">
    <div>
      <div className="sales-eyebrow"><p className="eyebrow muted">매출 증빙</p>
        {filing && <span className="sales-utility">
          <Link className="text-link" to={`/storage/trash?direction=sales&${salesPeriodQuery(period)}`}>휴지통</Link>
          {showSetup && <button className="text-link" disabled={busy} onClick={() => void submit("/validate")}>새로고침</button>}
        </span>}</div>
      <h1 className="screen-title">내 매출 내역을 확인하세요</h1>
      <VaultTabs purchaseTo={navigationPeriod ? `/storage/purchase?period=${encodeURIComponent(navigationPeriod)}` : "/storage/purchase"} salesTo={`/storage/sales${search.size ? `?${search}` : ""}`} />
      <label className="form-field period-picker sales-period"><span className="form-field__label">신고 대상 기간</span>
      <select className="input" value={selectedPeriod ? SALES_PERIODS[selectedPeriod].url : ""} disabled={busy} onChange={e => {
        const next = new URLSearchParams(search);
        next.set("period", e.target.value);
        next.delete("edit");
        setDuplicateChoices({});
        setSearch(next);
      }}>
        {!selectedPeriod && <option value="" disabled>신고 대상 기간 선택</option>}
        {salesPeriods.map(option => <option key={option} value={SALES_PERIODS[option].url}>{SALES_PERIODS[option].label}</option>)}
      </select></label>
    </div>
    {!selectedPeriod && <p className="banner banner--info">매출 확정은 2026년 반기를 지원합니다.</p>}
    {error && <p className="banner banner--info" role="alert">{error} {!filing && <Link to="/login">로그인</Link>}</p>}
    {busy && <p role="status" className="muted">매출 자료를 확인하는 중입니다.</p>}
    {selectedPeriod && filing?.period === selectedPeriod && <>
      {!showSetup && <section className="sales-hero" aria-label="신고기간 매출 금액">
        <span className="sales-hero__label">매출 금액</span>
        <strong className="sales-hero__amount">{formatWon(line?.supply_amount ?? 0)}</strong>
        {filing.status === "확정" && <Link className="sales-hero__link" to={`/reports?period=${period}`}>신고서 보기 ›</Link>}
      </section>}
      {!showSetup && duplicateIssues.length > 0 && (
        <SalesDuplicateCheckPanel
          issues={duplicateIssues}
          choices={duplicateChoices}
          onChoose={(issueId, choice) => setDuplicateChoices(current => ({ ...current, [issueId]: choice }))}
          onSave={() => void handleSaveDuplicateChoices()}
          busy={busy}
        />
      )}
      {showSetup && <section className="sales-setup" aria-label="출처별 자료">
        {sources.map(source => <SourceForm key={`${period}-${source[0]}-${JSON.stringify(filing.source_statuses[source[0]])}`} source={source}
          saved={filing.source_statuses[source[0]]}
          docs={docs.filter(doc => source[2].some(type => type === doc.document.매출증빙?.문서유형))}
          submit={submit} busy={busy} period={period} onConnected={connected}
          onDeleted={ids => setDocs(current => current.filter(doc => !ids.includes(doc.id)))} />)}
        <OtherSalesCard key={period} revision={filing.revision}
          sales={filing.other_sales ?? []} total={filing.other_sales_total} busy={busy} submit={submit} />
        {otherIssues.length > 0 && (
          <div className="banner banner--info sales-other-issues" role="status">
            {otherIssues.map(item => <div key={item.issue_id}>{item.question}</div>)}
          </div>
        )}
        <button type="button" className="btn btn--primary sales-setup-continue" disabled={busy}
          onClick={() => void confirmSales()}>{editingSources ? "수정 완료" : "매출 증빙 확정"}</button>
      </section>}
      {!showSetup && <section className="sales-monthly" aria-labelledby="sales-monthly-title">
        <div className="sales-monthly-heading">
          <h2 className="section-title" id="sales-monthly-title">월별 내역</h2>
          <button type="button" className="btn btn--primary sales-edit-button" onClick={() => setEditingSources(true)}>
            <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="m14 5 5 5M4 20l4.2-.8L19 8.4 15.6 5 4.8 15.8 4 20Z" /></svg>
            수정
          </button>
        </div>
        <ol className="sales-month-grid">
          {periodMonths.map(month => <li className="sales-month-card" key={month}>
            <time dateTime={month}>{Number(month.slice(5, 7))}월</time>
            <strong>{formatWon(monthTotals.get(month) ?? 0)}</strong>
          </li>)}
        </ol>
        {otherSalesTotal && <div className="sales-month-card sales-period-other-total">
          <span>반기 기타 매출</span>
          <strong>{formatWon(otherSalesTotal.supply_amount)}</strong>
        </div>}
      </section>}
    </>}
  </main></div>;
}
