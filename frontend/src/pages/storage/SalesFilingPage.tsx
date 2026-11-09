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
  ["unissued_sales", "증빙 미발급 매출", ["기타매출장"], "거래일"],
] as const;
const statuses = ["자료 없음", "검토 필요", "확인 완료", "해당 없음 확인"] as const;
type Source = typeof sources[number];
type Check = {status: typeof statuses[number]; query_start?: string; query_end?: string; basis?: string; reason?: string; document_ids: number[]};
type Issue = {source?: string; input_key?: string | null};
type Filing = {
  period: string; status: string; revision: number; reconfirmation_required: boolean;
  source_statuses: Record<string, Check>;
  issues: Issue[];
  aggregate: {lines?: Record<string, {supply_amount: number; vat_amount: number}>; included_rows?: {source: string; document_id: number | null}[]};
};
type Submit = (path: string, body?: object, method?: "post" | "put") => Promise<boolean>;
const field = (data: FormData, name: string) => String(data.get(name) ?? "").trim();
const amount = (data: FormData, name: string) => field(data, name) ? Number(field(data, name)) : null;

const sourceIconPaths = {
  hometax_card: "M3 6h18v12H3z M3 10h18 M6 14h4",
  hometax_cash_receipt: "M5 3h14v18l-3-2-4 2-4-2-3 2z M8 8h8 M8 12h8",
  hometax_sales_invoice: "M5 3h9l5 5v13H5z M14 3v5h5 M8 12h8 M8 16h8",
  pg: "M3 9l2-5h14l2 5 M3 9h18v2a3 3 0 0 1-6 0 3 3 0 0 1-6 0 3 3 0 0 1-6 0z M5 14v6h14v-6",
  unissued_sales: "M5 3h14v18H5z M8 8h8 M8 12h8 M8 16h4",
};

function SourceLabel({source, title, status, tone}: {source: Source[0]; title: string; status: string; tone?: "ready" | "review"}) {
  return <span className="sales-source-label">
    <span className="sales-source-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round"><path d={sourceIconPaths[source]} /></svg></span>
    <span className="sales-source-name"><strong>{title}</strong><small className="sales-source-status" data-tone={tone}>{status}</small></span>
  </span>;
}

function SourceForm({source, saved, docs, submit, busy, period, needsReview}: {
  source: Source; saved?: Check; docs: SavedDocument[]; submit: Submit; busy: boolean; period: SalesPeriod; needsReview: boolean;
}) {
  const [open, setOpen] = useState(false);
  const spreadsheetSource = source[0] === "hometax_card" ? "card" : source[0] === "hometax_cash_receipt" ? "cash" : source[0] === "hometax_sales_invoice" ? "invoice" : "pg";
  const linked = saved?.document_ids ?? [];
  const range = SALES_PERIODS[period];
  const firstMonth = range.start.slice(0, 7);
  const lastMonth = range.end.slice(0, 7);
  const pending = docs.find(doc => {
    const evidence = doc.document.매출증빙;
    if (!evidence || doc.status === "reviewed") return false;
    if (evidence.기간시작 && evidence.기간시작.slice(0, 7) > lastMonth) return false;
    if (evidence.기간종료 && evidence.기간종료.slice(0, 7) < firstMonth) return false;
    return evidence.내역.some(row => {
      const month = String(row.작성일 ?? row.일자또는월 ?? "").slice(0, 7);
      return month >= firstMonth && month <= lastMonth;
    });
  });
  const visible = linked.length ? docs.filter(doc => linked.includes(doc.id)) : pending ? [pending] : [];
  const status = linked.length ? needsReview ? "검증 보류" : "연결됨" : pending ? "연결 전" : saved?.status === "해당 없음 확인" ? "해당 없음" : "자료 없음";
  const documentPath = (doc: SavedDocument) => `/receipts/monthly/${doc.id}/review?${salesPeriodQuery(period)}${linked.includes(doc.id) ? "" : "&connect=1"}`;
  const direct = visible.length === 1 ? visible[0] : undefined;
  const controls = `sales-source-${source[0]}`;
  return <section className="sales-source sales-source--row">
    <div className="sales-source-row">
      <SourceLabel source={source[0]} title={source[1]} status={status} tone={linked.length ? needsReview ? "review" : "ready" : undefined} />
      <div className="sales-source-actions">
        {direct && <Link to={documentPath(direct)}>{linked.length ? "상세 보기" : "확인하고 연결"}</Link>}
        <button type="button" className={!linked.length && !direct ? "sales-source-upload" : undefined} aria-expanded={open} aria-controls={controls} onClick={() => setOpen(value => !value)}>
          {open ? "닫기" : linked.length ? visible.length > 1 ? "자료 관리" : "엑셀 교체" : "엑셀 올리기"}
        </button>
      </div>
    </div>
    <div className="sales-source__content" id={controls} hidden={!open}>
      {!direct && visible.map(doc => {
        const evidence = doc.document.매출증빙;
        const connected = linked.includes(doc.id);
        const dates = evidence?.기간시작 === range.start && evidence?.기간종료 === range.end ? range.label
          : evidence?.기간시작 && evidence.기간종료 ? `${evidence.기간시작} ~ ${evidence.기간종료}` : "조회기간 확인 전";
        return <Link className="sales-document-card" key={doc.id}
          to={documentPath(doc)}>
          <span className="sales-document-card__info">
            <strong>{spreadsheetSource === "invoice" ? "전자세금계산서 매출 목록" : source[1]}</strong>
            <small>{dates} · {evidence?.내역.length ?? 0}{spreadsheetSource === "invoice" ? "건" : "행"}</small>
          </span>
          <span className="sales-document-card__action">{connected ? "상세 보기" : "확인하고 연결"}</span>
        </Link>;
      })}
      <SpreadsheetUpload source={spreadsheetSource} period={period} replacing={linked.length > 0} />
    {!linked.length && saved?.status !== "해당 없음 확인" && <button type="button" className="btn btn--secondary" disabled={busy}
      onClick={() => void submit(`/sources/${source[0]}`, {
        status: "해당 없음 확인", document_ids: [], reason: "사업자가 선택한 신고기간에 해당 매출이 없음을 확인함.",
      }, "put")}>해당 매출 없음</button>}
    </div>
  </section>;
}

const spreadsheetLabels = {
  card: "월별 카드 매출 엑셀",
  cash: "현금영수증 매출내역누계 엑셀",
  invoice: "반기별 매출 전자세금계산서 목록 엑셀",
  pg: "홈택스 판매·결제대행 엑셀",
};

function SpreadsheetUpload({source, period, replacing}: {source: keyof typeof spreadsheetLabels; period: SalesPeriod; replacing: boolean}) {
  const navigate = useNavigate();
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [fileName, setFileName] = useState("");
  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (uploading || !fileName) return;
    const body = new FormData(event.currentTarget);
    body.set("source", source);
    setUploading(true);
    setError("");
    try {
      const {data} = await apiClient.post<SavedDocument>("/sales/monthly/spreadsheet", body);
      navigate(`/receipts/monthly/${data.id}/review?${salesPeriodQuery(period)}&connect=1${replacing ? "&replace=1" : ""}`);
    } catch (e) {
      setError(isAxiosError(e) ? e.response?.data?.error?.message ?? "엑셀을 올리지 못했습니다." : "엑셀을 올리지 못했습니다.");
    } finally {setUploading(false);}
  }
  return <form className="sales-form" onSubmit={upload}>
    <label className="sales-file-picker">
      <input className="sr-only" aria-label={spreadsheetLabels[source]} name="file" type="file" accept=".xls,.xlsx" required
        onChange={event => { setFileName(event.currentTarget.files?.[0]?.name ?? ""); setError(""); }} />
      <span>{fileName ? "다른 파일 선택" : "엑셀 파일 선택"}</span>
    </label>
    {fileName && <p className="muted sales-file-name" role="status">{fileName}</p>}
    <button className="btn btn--secondary" disabled={uploading || !fileName}>{uploading ? "엑셀 읽는 중" : replacing ? "새 엑셀 가져오기" : "엑셀 가져오기"}</button>
    {error && <p role="alert">{error}</p>}
  </form>;
}

function UnissuedSalesForm({saved, docs, hasManualEntries, submit, busy, period}: {
  saved?: Check; docs: SavedDocument[]; hasManualEntries: boolean; submit: Submit; busy: boolean; period: SalesPeriod;
}) {
  const [answer, setAnswer] = useState(saved?.status === "해당 없음 확인" ? "no" : saved?.status === "확인 완료" ? "yes" : "");
  const [method, setMethod] = useState(saved?.document_ids.length ? "document" : "manual");
  const [selected, setSelected] = useState(saved?.document_ids ?? []);
  const label = saved?.status === "해당 없음 확인" ? "없음 확인" : saved?.status === "확인 완료" ? "내역 등록 완료" : "확인 전";
  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    void submit("/sources/unissued_sales", {
      status: answer === "no" ? "해당 없음 확인" : "확인 완료",
      reason: answer === "no" ? "사업자가 해당 신고기간의 증빙 미발급 매출이 없음을 확인함." : null,
      query_start: field(data, "start") || null, query_end: field(data, "end") || null,
      basis: method === "document" && answer === "yes" ? field(data, "basis") : null,
      document_ids: data.getAll("docs").map(Number),
    }, "put");
  }
  return <details className="sales-source sales-source--unissued">
    <summary className="sales-source-row"><SourceLabel source="unissued_sales" title="증빙 미발급 매출" status={label} /><span className="sales-source-summary-action">내역 입력</span></summary>
    <fieldset className="sales-choices">
      <legend>이번 신고기간에 현금이나 계좌이체로 받고, 현금영수증과 세금계산서를 모두 발급하지 않은 판매가 있었나요?</legend>
      <label><input type="radio" name="unissued-answer" checked={answer === "no"} onChange={() => setAnswer("no")} /> 없어요</label>
      <label><input type="radio" name="unissued-answer" checked={answer === "yes"} onChange={() => setAnswer("yes")} /> 있어요</label>
    </fieldset>
    {answer === "no" && <form className="sales-form" onSubmit={save}>
      <button className="btn btn--secondary" disabled={busy}>없음으로 저장</button>
    </form>}
    {answer === "yes" && <>
      <fieldset className="sales-choices">
        <legend>매출 내역 등록 방법</legend>
        <label><input type="radio" name="unissued-method" checked={method === "manual"} onChange={() => setMethod("manual")} /> 직접 입력</label>
        <label><input type="radio" name="unissued-method" checked={method === "document"} onChange={() => setMethod("document")} /> 매출장 연결</label>
      </fieldset>
      <p className="sales-source-help muted">같은 거래는 한 가지 방법으로만 등록하세요.</p>
      {method === "manual" && <ManualSaleForm submit={submit} busy={busy} />}
      <form className="sales-form" onSubmit={save}>
        {method === "document" && <>
          <p className="muted">미발급 매출이 구분된 매출장이나 판매내역을 연결하세요.</p>
          <Link className="text-link" to="/capture?direction=sales">매출장 사진 등록</Link>
          <div className="sales-fields">
            <label>자료 시작일<input className="input" name="start" type="date" defaultValue={saved?.query_start} required /></label>
            <label>자료 종료일<input className="input" name="end" type="date" defaultValue={saved?.query_end} required /></label>
          </div>
          <label>자료의 날짜 기준<input className="input" name="basis" defaultValue={saved?.basis ?? "거래일"} required /></label>
          <fieldset className="sales-docs"><legend>연결할 매출장</legend>
            {!docs.length && <p className="muted">등록된 매출장이 없어요.</p>}
            {docs.map(doc => <div key={doc.id}>
              <label><input type="checkbox" name="docs" value={doc.id} checked={selected.includes(doc.id)} disabled={doc.status !== "reviewed"}
                onChange={e => setSelected(e.target.checked ? [...selected, doc.id] : selected.filter(id => id !== doc.id))} /> 문서 {doc.id} · {doc.document.매출증빙?.기간시작 ?? doc.created_at.slice(0, 10)}</label>
              <Link to={`/receipts/monthly/${doc.id}/review?${salesPeriodQuery(period)}`}>내용 확인</Link>
            </div>)}
          </fieldset>
        </>}
        <button className="btn btn--secondary" disabled={busy || (method === "document" ? !docs.some(doc => doc.status === "reviewed" && selected.includes(doc.id)) : !hasManualEntries)}>
          {method === "document" ? "매출장 연결 완료" : "신고기간 내역을 모두 입력했어요"}
        </button>
      </form>
    </>}
  </details>;
}

function ManualSaleForm({submit, busy}: {submit: Submit; busy: boolean}) {
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const saved = await submit("/inputs", {
      input_key: crypto.randomUUID(), source: "unissued_sales", tax_treatment: "과세",
      date: field(data, "date"), payment_method: field(data, "payment"), total_amount: amount(data, "total"),
      supporting_evidence: field(data, "evidence"),
    });
    if (saved) form.reset();
  }
  return <div className="sales-manual">
    <h3>매출 내역 직접 입력</h3>
    <p className="muted">주문·판매내역을 참고해 실제 판매대금만 입력하세요.</p>
    <form className="sales-form" onSubmit={save}>
      <div className="sales-fields">
        <label>거래일<input className="input" name="date" type="date" required /></label>
        <label>결제수단<select className="input" name="payment"><option>현금</option><option>계좌이체</option></select></label>
        <label>부가세 포함 금액<input className="input" name="total" type="number" min="1" step="1" required /></label>
      </div>
      <label>미발급 확인 근거<input className="input" name="evidence" maxLength={2000} required /></label>
      <button className="btn btn--secondary" disabled={busy}>미발급 매출 저장</button>
    </form>
  </div>;
}

export function SalesFilingPage() {
  const [search, setSearch] = useSearchParams();
  const requestedPeriod = search.get("period");
  const selectedPeriod = parseSalesPeriod(requestedPeriod) ?? (!requestedPeriod || requestedPeriod === "all" ? "2026-H1" : undefined);
  const period = selectedPeriod ?? "2026-H1";
  const [filing, setFiling] = useState<Filing | null>(null);
  const [docs, setDocs] = useState<SavedDocument[]>([]);
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
  return <div className="page qa-page sales-filing-page"><PageHeader title="매출 보관함" showAmountToggle /><main className="page__body sales-filing">
    <div>
      <p className="eyebrow muted">매출 증빙 및 거래 관리</p>
      <h1 className="screen-title">내 매출 내역을 확인하세요</h1>
      <nav className="vault-tabs" aria-label="보관함 종류"><NavLink to={`/storage/purchase?period=${period}`}>매입</NavLink><NavLink to={`/storage/sales?${salesPeriodQuery(period)}`}>매출</NavLink></nav>
      <label className="form-field period-picker sales-period"><span className="form-field__label">신고 대상 기간</span>
      <select className="input" value={selectedPeriod ? SALES_PERIODS[selectedPeriod].url : ""} disabled={busy} onChange={e => {
        const next = new URLSearchParams(search);
        next.set("period", e.target.value);
        setSearch(next);
      }}>
        {!selectedPeriod && <option value="" disabled>신고 대상 기간 선택</option>}
        {salesPeriods.map(option => <option key={option} value={SALES_PERIODS[option].url}>{SALES_PERIODS[option].label}</option>)}
      </select></label>
    </div>
    {!selectedPeriod && <p className="banner banner--info">매출 자료는 2026년 1~6월과 7~12월로 나누어 확인할 수 있습니다. 확인할 기간을 선택해 주세요.</p>}
    {error && <p className="banner banner--info" role="alert">{error} {!filing && <Link to="/login">로그인</Link>}</p>}
    {busy && <p role="status" className="muted">매출 자료를 확인하는 중입니다.</p>}
    {selectedPeriod && filing?.period === selectedPeriod && <>
      {line && filing.status !== "검토 필요" && <section className="sales-total" aria-label="신고용 집계">
        <small className="muted">{filing.status === "확정" ? "확정 과세표준" : "검토 중 과세표준"} · 공급가액</small>
        <strong>{fmt.won(line.supply_amount)}</strong>
      </section>}
      <section aria-labelledby="sales-sources-title">
        <div className="section-heading"><h2 className="section-title" id="sales-sources-title">출처별 자료</h2></div>
        {sources.filter(source => source[0] !== "unissued_sales").map(source => <SourceForm key={`${period}-${source[0]}-${JSON.stringify(filing.source_statuses[source[0]])}`} source={source}
          saved={filing.source_statuses[source[0]]}
          docs={docs.filter(doc => source[2].some(type => type === doc.document.매출증빙?.문서유형))}
          submit={submit} busy={busy} period={period} needsReview={filing.issues.some(issue => issue.source === source[0])} />)}
        <UnissuedSalesForm key={period} period={period} saved={filing.source_statuses.unissued_sales}
          hasManualEntries={filing.issues.some(issue => issue.source === "unissued_sales" && !!issue.input_key && !issue.input_key.startsWith("document:"))
            || !!filing.aggregate.included_rows?.some(row => row.source === "unissued_sales" && row.document_id === null)}
          docs={docs.filter(doc => doc.document.매출증빙?.문서유형 === "기타매출장")} submit={submit} busy={busy} />
      </section>
      <div className="vault-actions">
        <Link className="btn btn--secondary" to={`/capture?direction=sales&${salesPeriodQuery(period)}`}>＋ 매출 증빙 추가</Link>
        {filing.status === "확정" && <Link className="btn btn--primary" to={`/reports?period=${period}`}>신고서 보기</Link>}
      </div>
      <div className="section-heading utility-row">
        <Link className="text-link" to="/storage/trash?direction=sales">휴지통</Link>
        <button className="text-link" disabled={busy} onClick={() => void submit("/validate")}>새로고침</button>
      </div>
    </>}
  </main></div>;
}
