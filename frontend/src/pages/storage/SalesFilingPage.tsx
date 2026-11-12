import { useEffect, useState, type FormEvent } from "react";
import { isAxiosError } from "axios";
import { Link, NavLink, useNavigate, useSearchParams } from "react-router-dom";
import { apiClient } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import type { SavedDocument } from "../../components/MonthlySalesReview";
import { useMaskedFormat } from "../../hooks/useMaskedFormat";
import { SALES_PERIODS, friendlySalesPeriods, parseSalesPeriod, salesPeriodQuery, salesPeriods, type SalesPeriod } from "../../hooks/salesPeriod";
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
type Issue = {source?: string; input_key?: string | null};
type Filing = {
  period: string; status: string; revision: number; reconfirmation_required: boolean;
  source_statuses: Record<string, Check>;
  issues: Issue[];
  aggregate: {lines?: Record<string, {supply_amount: number; vat_amount: number; total_amount?: number}>; included_rows?: IncludedSalesRow[]};
};
type IncludedSalesRow = {source: string; document_id: number | null; date?: string | null; supply_amount: number; total_amount: number};
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
};

function SourceLabel({source, title, status, tone}: {source: Source[0]; title: string; status: string; tone?: "ready"}) {
  return <span className="sales-source-label">
    <span className="sales-source-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round"><path d={sourceIconPaths[source]} /></svg></span>
    <span className="sales-source-name"><strong>{title}</strong><small className="sales-source-status" data-tone={tone}>{status}</small></span>
  </span>;
}

function SourceForm({source, saved, docs, submit, busy, period}: {
  source: Source; saved?: Check; docs: SavedDocument[]; submit: Submit; busy: boolean; period: SalesPeriod;
}) {
  const [openPanel, setOpenPanel] = useState<"details" | "replace" | null>(null);
  const linked = saved?.document_ids ?? [];
  const linkedDocs = docs.filter(doc => linked.includes(doc.id));
  const status = linked.length ? "연결됨" : "연결 안 됨";
  const documentPath = (doc: SavedDocument) => `/receipts/monthly/${doc.id}/review?${salesPeriodQuery(period)}`;
  const direct = linkedDocs.length === 1 ? linkedDocs[0] : undefined;
  const canMarkNone = !linked.length && !resolvedSourceStatuses.has(saved?.status ?? "");
  const controls = `sales-source-${source[0]}`;
  return <section className="sales-source sales-source--row">
    <div className="sales-source-row">
      <SourceLabel source={source[0]} title={source[1]} status={status}
        tone={linked.length ? "ready" : undefined} />
      <div className="sales-source-actions">
        {canMarkNone && <button type="button" className="sales-source-none" disabled={busy}
          onClick={() => void submit("/sources/" + source[0], {
            status: "해당 없음 확인", document_ids: [], reason: "사업자가 선택한 신고기간에 해당 매출이 없음을 확인함.",
          }, "put")}>자료 없음</button>}
        {direct && <Link to={documentPath(direct)}>상세 보기</Link>}
        {linkedDocs.length > 1 && <button type="button" aria-expanded={openPanel === "details"} aria-controls={controls}
          onClick={() => setOpenPanel(value => value === "details" ? null : "details")}>
          {openPanel === "details" ? "닫기" : "자료 보기"}
        </button>}
        {linked.length > 0 && <button type="button" className="sales-source-replace" aria-expanded={openPanel === "replace"} aria-controls={controls}
          onClick={() => setOpenPanel(value => value === "replace" ? null : "replace")}>
          {openPanel === "replace" ? "닫기" : "엑셀 교체"}
        </button>}
      </div>
    </div>
    {openPanel && <div className="sales-source__content" id={controls}>
      {openPanel === "details" && linkedDocs.map(doc => {
        const evidence = doc.document.매출증빙;
        return <Link className="sales-document-card" key={doc.id} to={documentPath(doc)}>
          <span className="sales-document-card__info"><strong>{source[1]}</strong>
            <small>{doc.created_at.slice(0, 10)} · {evidence?.내역.length ?? 0}행</small></span>
          <span className="sales-document-card__action">상세 보기</span>
        </Link>;
      })}
      {openPanel === "replace" && <SpreadsheetReplace source={( {
        hometax_card: "card", hometax_cash_receipt: "cash", hometax_sales_invoice: "invoice", pg: "pg",
      } as const)[source[0]]} period={period} />}
    </div>}
  </section>;
}

function SpreadsheetReplace({source, period}: {source: keyof typeof spreadsheetLabels; period: SalesPeriod}) {
  const navigate = useNavigate();
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [fileName, setFileName] = useState("");
  async function replace(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (uploading || !fileName) return;
    const body = new FormData(event.currentTarget);
    body.set("source", source);
    setUploading(true);
    setError("");
    try {
      const {data} = await apiClient.post<SavedDocument>("/sales/monthly/spreadsheet", body);
      navigate(`/receipts/monthly/${data.id}/review?${salesPeriodQuery(period)}&connect=1&replace=1`);
    } catch (e) {
      setError(isAxiosError(e) ? e.response?.data?.error?.message ?? "엑셀을 올리지 못했습니다." : "엑셀을 올리지 못했습니다.");
    } finally { setUploading(false); }
  }
  return <form className="sales-form" onSubmit={replace}>
    <label className="sales-file-picker">
      <input className="sr-only" aria-label={spreadsheetLabels[source]} name="file" type="file" accept=".xls,.xlsx" required
        onChange={event => { setFileName(event.currentTarget.files?.[0]?.name ?? ""); setError(""); }} />
      <span>{fileName ? "다른 파일 선택" : "엑셀 파일 선택"}</span>
    </label>
    {fileName && <p className="muted sales-file-name" role="status">{fileName}</p>}
    <button className="btn btn--secondary" disabled={uploading || !fileName}>{uploading ? "엑셀 읽는 중" : "새 엑셀로 교체"}</button>
    {error && <p role="alert">{error}</p>}
  </form>;
}

export function SalesFilingPage() {
  const [search, setSearch] = useSearchParams();
  const requestedPeriod = search.get("period");
  const selectedPeriod = parseSalesPeriod(requestedPeriod) ?? (!requestedPeriod || requestedPeriod === "all" ? "2026-H1" : undefined);
  const period = selectedPeriod ?? "2026-H1";
  const [filing, setFiling] = useState<Filing | null>(null);
  const [docs, setDocs] = useState<SavedDocument[]>([]);
  const [editingSources, setEditingSources] = useState(false);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const fmt = useMaskedFormat();
  const path = `/sales/filings/${period}`;
  useEffect(() => {
    if (!selectedPeriod || requestedPeriod === SALES_PERIODS[selectedPeriod].url) return;
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
  const line = filing?.aggregate.lines?.["9"];
  const sourceCompleteCount = filing
    ? sources.filter(source => resolvedSourceStatuses.has(filing.source_statuses[source[0]]?.status ?? "")).length
    : 0;
  const allSourcesComplete = sourceCompleteCount === sources.length;
  const showSetup = !allSourcesComplete || editingSources;
  const periodMonths = selectedPeriod ? monthsInPeriod(selectedPeriod) : [];
  const monthTotals = new Map<string, number>(periodMonths.map(month => [month, 0] as [string, number]));
  const includedRows = filing?.aggregate.included_rows ?? [];
  includedRows.forEach(row => {
    const month = monthForRowDate(row.date);
    if (month && monthTotals.has(month)) monthTotals.set(month, (monthTotals.get(month) ?? 0) + row.supply_amount);
  });
  const navigationPeriod = selectedPeriod ?? requestedPeriod;
  return <div className="page qa-page sales-filing-page"><PageHeader title="매출 보관함" showAmountToggle /><main className="page__body sales-filing">
    <div>
      <h1 className="screen-title">{showSetup ? "내 매출 내역을 확인하세요" : "월별 매출"}</h1>
      <nav className="vault-tabs" aria-label="보관함 종류"><NavLink to={navigationPeriod ? `/storage/purchase?period=${encodeURIComponent(navigationPeriod)}` : "/storage/purchase"}>매입</NavLink><NavLink to={`/storage/sales${search.size ? `?${search}` : ""}`}>매출</NavLink></nav>
      <label className="form-field period-picker sales-period"><span className="form-field__label">신고 대상 기간</span>
      <select className="input" value={selectedPeriod ? SALES_PERIODS[selectedPeriod].url : ""} disabled={busy} onChange={e => {
        setEditingSources(false);
        const next = new URLSearchParams(search);
        next.set("period", e.target.value);
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
      {!showSetup && line && <section className="sales-total sales-archive-total" aria-label="신고기간 공급가액 합계">
        <strong>{fmt.won(line.supply_amount)}</strong>
      </section>}
      {showSetup && <section aria-labelledby="sales-sources-title">
        <div className="section-heading"><h2 className="section-title" id="sales-sources-title">출처별 자료</h2></div>
        {sources.map(source => <SourceForm key={`${period}-${source[0]}-${JSON.stringify(filing.source_statuses[source[0]])}`} source={source}
          saved={filing.source_statuses[source[0]]}
          docs={docs.filter(doc => source[2].some(type => type === doc.document.매출증빙?.문서유형))}
          submit={submit} busy={busy} period={period} />)}
        <div className="sales-setup-footer">
          <div className="sales-progress">
            <span>자료 확인 {sourceCompleteCount}/{sources.length}</span>
            <progress value={sourceCompleteCount} max={sources.length} aria-label="자료 확인 진행"></progress>
          </div>
          <button type="button" className="btn btn--secondary sales-setup-continue" disabled={busy || !allSourcesComplete}
            onClick={() => setEditingSources(false)}>{editingSources ? "수정 완료" : "매출 보관함 보기"}</button>
        </div>
      </section>}
      {!showSetup && <section className="sales-monthly" aria-labelledby="sales-monthly-title">
        <div className="section-heading sales-monthly-heading">
          <h2 className="section-title" id="sales-monthly-title">월별 내역</h2>
        </div>
        <ol className="sales-month-track">
          {periodMonths.map(month => <li className="sales-month-card" key={month}>
            <time dateTime={month}>{Number(month.slice(5, 7))}월</time>
            <span className="sales-month-amount">
              <strong>{fmt.won(monthTotals.get(month) ?? 0)}</strong>
            </span>
          </li>)}
        </ol>
      </section>}
      {!showSetup && filing.status === "확정" && <div className="vault-actions">
        <Link className="btn btn--primary" to={`/reports?period=${period}`}>신고서 보기</Link>
      </div>}
      <div className="section-heading utility-row">
        <Link className="text-link" to={`/storage/trash?direction=sales&${salesPeriodQuery(period)}`}>휴지통</Link>
        {showSetup
          ? <button className="text-link" disabled={busy} onClick={() => void submit("/validate")}>새로고침</button>
          : <button type="button" className="btn btn--primary sales-edit-button" onClick={() => setEditingSources(true)}>
            <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="m14 5 5 5M4 20l4.2-.8L19 8.4 15.6 5 4.8 15.8 4 20Z" /></svg>
            수정
          </button>}
      </div>
    </>}
  </main></div>;
}
