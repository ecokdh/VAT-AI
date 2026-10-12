import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getAnalysisRun, listTransactions, type AnalysisRunApi, type TransactionApi } from "../../api/transactions";
import { PageHeader } from "../../components/PageHeader";

type Reference = { source_id: string; title: string; locator?: string; url?: string; effective_date?: string };
type Result = { transaction_id: number; description?: string; vendor?: string; transaction_date?: string; revision?: number; status: string; reason?: string; missing_information?: string[]; legal_references?: Reference[] };
const groups = [{ key: "possible", title: "공제 가능" }, { key: "review", title: "애매 · 검토 필요" }, { key: "impossible", title: "공제 불가능" }] as const;
function groupOf(item: Result) { return item.status === "DEDUCTIBLE" ? "possible" : item.status === "NOT_DEDUCTIBLE" ? "impossible" : "review"; }
function sourceUrl(value?: string) { try { const url = new URL(value ?? ""); return ["https:", "http:"].includes(url.protocol) ? url.href : undefined; } catch { return undefined; } }

export function AnalysisResultPage() {
  const { runId } = useParams();
  const [run, setRun] = useState<AnalysisRunApi | null>(null);
  const [rows, setRows] = useState<TransactionApi[]>([]);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [visible, setVisible] = useState<Record<string, number>>({ possible: 5, review: 5, impossible: 5 });
  const [selected, setSelected] = useState<Result | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (!runId) return;
    let active = true;
    let timer: number | undefined;
    async function poll() {
      try {
        const result = await getAnalysisRun(runId!);
        if (!active) return;
        setRun(result);
        if (result.status === "PENDING" || result.status === "PROCESSING") timer = window.setTimeout(poll, 1000);
        else if (result.status === "COMPLETED") {
          const transactions = await listTransactions("purchase");
          if (active) setRows(transactions);
        }
      } catch { if (active) setError("분석 상태를 불러오지 못했습니다. 연결을 확인한 후 다시 시도해 주세요."); }
    }
    void poll();
    return () => { active = false; window.clearTimeout(timer); };
  }, [runId, retry]);
  useEffect(() => { if (selected) dialog.current?.showModal(); else dialog.current?.close(); }, [selected]);
  let results: Result[] = [];
  let invalid = false;
  if (run?.status === "COMPLETED") {
    try {
      const parsed: unknown = JSON.parse(run.result_json ?? "null");
      if (!Array.isArray(parsed) || !parsed.every((item) => item && typeof item.transaction_id === "number" && typeof item.status === "string")) throw new Error();
      results = parsed;
    } catch { invalid = true; }
  }
  function memo(item: Result) {
    const row = rows.find((transaction) => transaction.id === item.transaction_id);
    return item.description || (item.vendor ? `${item.transaction_date ?? ""} ${item.vendor}` : row?.description || (row ? `${row.transaction_date} ${row.vendor}` : `거래 #${item.transaction_id}`));
  }
  const pending = !run || run.status === "PENDING" || run.status === "PROCESSING";
  return <div className="page"><PageHeader title="공제 분석" /><div className="page__body">
    {!runId ? <div className="banner banner--warning">매입 보관함에서 거래를 선택해 분석해 주세요.</div> : <>
      {error && <div className="banner banner--error" role="alert">{error}<button className="btn btn--secondary" onClick={() => { setError(""); setRetry((value) => value + 1); }}>상태 다시 확인</button></div>}
      {pending && !error && <section className="analysis-loading" role="status"><div className="analysis-spinner" /><h1 className="screen-title">공제 여부 분석 중</h1><p className="muted">거래 정보와 판단 근거를 확인하고 있어요.</p><ol><li>선택한 거래 확인</li><li>공제 요건 및 근거 확인</li><li>결과 정리</li></ol><p className="muted">{run?.status === "PENDING" ? "분석 순서를 기다리고 있습니다." : "작업이 끝나면 결과가 표시됩니다."}</p></section>}
      {run?.status === "FAILED" && <div className="banner banner--error" role="alert">{run.error_message ?? "분석에 실패했습니다. 보관함에서 다시 요청해 주세요."}</div>}
      {invalid && <p role="alert">분석 결과 형식을 확인할 수 없습니다. 다시 조회해 주세요.</p>}
      {run?.status === "COMPLETED" && !invalid && <>
        <h1 className="screen-title">분석 결과를 확인해 주세요</h1><p className="muted">애매한 거래를 누르면 판단 이유와 근거를 확인할 수 있어요. 검토가 필요한 거래는 예상 공제액에서 제외됩니다.</p>
        {groups.map((group) => {
          const items = results.filter((item) => groupOf(item) === group.key);
          return <section className={`result-group result-group--${group.key}`} key={group.key}><h2>{group.title} <span>{items.length}건</span></h2>
            {items.length === 0 && <p className="muted">해당 거래가 없습니다.</p>}
            {items.slice(0, visible[group.key]).map((item) => <div key={item.transaction_id} className="result-row">{group.key === "review" ? <button onClick={() => setSelected(item)} aria-haspopup="dialog"><span>{memo(item)}</span><span>›</span></button> : <span>{memo(item)}</span>}</div>)}
            {items.length > visible[group.key] && <button className="btn btn--ghost" onClick={() => setVisible((current) => ({ ...current, [group.key]: current[group.key] + 5 }))}>더보기 ({items.length - visible[group.key]}건)</button>}
          </section>;
        })}
      </>}
    </>}
    <Link className="btn btn--secondary" style={{ marginTop: 24 }} to="/storage/purchase">매입 보관함으로</Link>
  </div>
  <dialog ref={dialog} className="analysis-peek" aria-labelledby="analysis-detail-title" onCancel={() => setSelected(null)} onClose={() => setSelected(null)} onClick={(event) => { if (event.target === event.currentTarget) setSelected(null); }}>
    {selected && <div><header className="peek-header"><strong id="analysis-detail-title">분석 상세</strong><button className="icon-btn" aria-label="상세 닫기" onClick={() => setSelected(null)}>×</button></header><h2>{memo(selected)}</h2>
      <p className="banner banner--warning">{selected.status === "SKIPPED_STALE" ? "분석 중 거래가 변경되거나 삭제되어 제외했습니다. 보관함에서 다시 확인해 주세요." : selected.reason ?? "추가 확인이 필요합니다."}</p>
      {!!selected.missing_information?.length && <><h3>확인이 필요한 정보</h3><ul>{selected.missing_information.map((field) => <li key={field}>{field}</li>)}</ul></>}
      <h3>판례·세법 근거</h3>
      {selected.legal_references?.length ? selected.legal_references.map((ref, index) => <article className="card" key={`${ref.source_id}-${index}`}><strong>{ref.title}</strong><p>{ref.locator}</p><p className="muted">출처: {ref.source_id}{ref.effective_date ? ` · 시행일 ${ref.effective_date}` : ""}</p>{sourceUrl(ref.url) && <a href={sourceUrl(ref.url)} target="_blank" rel="noreferrer" className="source-link">근거 원문 열기 ↗</a>}</article>) : <p className="muted">연결된 근거 자료가 없습니다. 이 결과는 공제 확정에 사용할 수 없습니다.</p>}
    </div>}
  </dialog></div>;
}
