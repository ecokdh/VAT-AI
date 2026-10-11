import { useCallback, useEffect, useState } from "react";
import { isAxiosError } from "axios";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { getMe } from "../../api/auth";
import { createAnalysisRun, getTaxEstimate, getTaxProfile, listTransactions, moveTransactionToTrash, saveTaxProfile, type TaxEstimateApi, type TaxProfileApi, type TaxProfileInput, type TransactionApi } from "../../api/transactions";
import { useMaskedFormat } from "../../hooks/useMaskedFormat";
import { PageHeader } from "../../components/PageHeader";
import { DeleteConfirmation } from "../../components/DeleteConfirmation";
import { listReceiptInbox, type ReceiptProcessingApi } from "../../api/receipts";

const won = (value: number | null) => value == null ? "확인 필요" : `${value.toLocaleString()}원`;

export function PurchaseTransactionStoragePage({ direction = "purchase" }: { direction?: "purchase" | "sales" }) {
  const location = useLocation();
  const fmt = useMaskedFormat();
  const [month, setMonth] = useState("");
  const [order, setOrder] = useState("newest");
  const [status, setStatus] = useState("all");
  const purchase = direction === "purchase";
  const [transactions, setTransactions] = useState<TransactionApi[]>([]);
  const [receiptInbox, setReceiptInbox] = useState<ReceiptProcessingApi[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [estimate, setEstimate] = useState<TaxEstimateApi | null>(null);
  const [period, setPeriod] = useState("2026-H1");
  const [taxType, setTaxType] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [taxProfile, setTaxProfile] = useState<TaxProfileApi | null>(null);
  const [profileSaving, setProfileSaving] = useState(false);
  const navigate = useNavigate();
  const [deleteTarget, setDeleteTarget] = useState<TransactionApi | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const rows = await listTransactions(direction);
      setTransactions(rows);
      setSelected((ids) => ids.filter((id) => rows.some((row) => row.id === id)));
      setReceiptInbox((await listReceiptInbox()).filter((receipt) => receipt.direction === direction));
      if (!purchase) return;
      setTaxProfile(await getTaxProfile());
      const user = await getMe();
      const simplified = user.business?.tax_type_code === "02";
      setTaxType(simplified ? "simplified" : user.business?.tax_type_code === "01" ? "general" : null);
      const nextPeriod = simplified ? "2026-YEAR" : new Date().getMonth() < 6 ? "2026-H1" : "2026-H2";
      setPeriod(nextPeriod);
      if (user.business?.tax_type_code === "01" || simplified) {
        setEstimate(await getTaxEstimate(nextPeriod));
      }
    } catch (error) {
      setMessage(isAxiosError(error) ? error.response?.data?.error?.message ?? "거래를 불러오지 못했습니다." : "거래를 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }, [direction, purchase]);

  useEffect(() => { void refresh(); }, [refresh]);

  async function analyzeSelected() {
    if (selected.length === 0) return;
    setBusy(true);
    setMessage("");
    try {
      const current = await createAnalysisRun(selected);
      navigate(`/analysis/${current.id}`);
    } catch (error) {
      setMessage(isAxiosError(error) ? error.response?.data?.error?.message ?? "분석 작업을 시작하지 못했습니다." : "분석 작업을 시작하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }

  async function removeTransaction(id: number) {
    if (deleting) return;
    setDeleting(true);
    setDeleteError("");
    try {
      await moveTransactionToTrash(id);
      setDeleteTarget(null);
      setSelected((current) => current.filter((selectedId) => selectedId !== id));
      await refresh();
      setMessage("거래를 휴지통으로 옮겼습니다. 예상 세액 집계에서 제외했습니다.");
    } catch {
      setDeleteError("거래를 휴지통으로 옮기지 못했습니다. 다시 시도해 주세요.");
    } finally {
      setDeleting(false);
    }
  }

  const periodOptions = taxType === "simplified" ? ["2026-YEAR"] : ["2026-H1", "2026-H2"];

  async function changePeriod(value: string) {
    setPeriod(value);
    try { setEstimate(await getTaxEstimate(value)); }
    catch { setMessage("예상 세액을 계산하지 못했습니다."); }
  }

  async function saveProfile(confirmed: boolean) {
    if (!taxProfile) return;
    setProfileSaving(true);
    setMessage("");
    try {
      const input: TaxProfileInput = { ...taxProfile, confirmed };
      setTaxProfile(await saveTaxProfile(input));
      setMessage(confirmed ? "사업자·과세기간 정보를 확인했습니다." : "사업자 정보를 저장했습니다. 확인 전에는 세율·공제 한도 판단에 사용하지 않습니다.");
      if (confirmed) await refresh();
    } catch (error) {
      setMessage(isAxiosError(error) ? error.response?.data?.error?.message ?? "사업자 정보를 저장하지 못했습니다." : "사업자 정보를 저장하지 못했습니다.");
    } finally {
      setProfileSaving(false);
    }
  }

  function updateProfile<K extends keyof TaxProfileApi>(key: K, value: TaxProfileApi[K]) {
    setTaxProfile((current) => current ? { ...current, [key]: value, confirmed: false } : current);
  }

  const statusLabels: Record<string, string> = { pending: "분석 전", not_analyzed: "분석 전", analyzed: "공제 가능", caution: "애매 · 검토 필요", insufficient_info: "정보 부족", excluded: "공제 불가능", stale: "재분석 필요" };
  const filtered = transactions.filter((item) => (!month || item.transaction_date.startsWith(month)) && (status === "all" || item.review_status === status)).sort((a, b) => order === "amount" ? b.total_amount - a.total_amount : order === "oldest" ? a.transaction_date.localeCompare(b.transaction_date) : b.transaction_date.localeCompare(a.transaction_date));

  return (
    <div className="page">
      <PageHeader title="거래 보관함" showAmountToggle />
      <div className="page__body">
        <nav className="vault-tabs" aria-label="보관함 종류"><NavLink to="/storage/purchase">매입</NavLink><NavLink to="/storage/sales">매출</NavLink></nav>
        {location.state?.transactionSaved && <p className="banner banner--info" role="status">거래를 보관함에 저장했습니다.</p>}
        <section className={`summary-card ${purchase ? "summary-card--primary" : "summary-card--sales"}`}><div>{purchase ? "매입" : "매출"} 거래 총액</div><h2>{fmt.won(transactions.reduce((sum, row) => sum + row.total_amount, 0))}</h2><span>{transactions.length}건의 거래</span></section>
        <button className="btn btn--secondary" style={{ margin: "16px 0" }} onClick={() => navigate(`/capture?direction=${direction}`)}>증빙 추가하기</button>
        {purchase && estimate && (
          <section className="card" style={{ marginBottom: 16 }}>
            <label className="form-field__label" htmlFor="tax-period">2026 신고 기간</label>
            <select id="tax-period" className="input" value={period} onChange={(event) => void changePeriod(event.target.value)}>
              {periodOptions.map((option) => <option key={option} value={option}>{option === "2026-YEAR" ? "간이과세 연간" : option === "2026-H1" ? "일반과세 1기" : "일반과세 2기"}</option>)}
            </select>
            <div className="field-row"><span className="field-row__label">예상 납부세액</span><strong>{won(estimate.payable_estimate)}</strong></div>
            <div className="field-row"><span className="field-row__label">매입 공제액</span><span>{won(estimate.eligible_input_vat)} · 의제매입 {won(estimate.deemed_input_vat)}</span></div>
            <div className="field-row"><span className="field-row__label">계산 상태</span><span>{estimate.status} · 검토 {estimate.caution_transaction_count}건 · 미계산 {estimate.uncalculated_transaction_count}건</span></div>
            {estimate.notes.map((note) => <p key={note} className="muted">{note}</p>)}
          </section>
        )}
        {purchase && !estimate && !loading && <div className="banner banner--warning">사업자의 국세청 과세유형을 확인해야 예상 세액을 계산할 수 있습니다.</div>}
        {purchase && taxProfile && (
          <details className="card" style={{ marginBottom: 16 }}>
            <summary style={{ cursor: "pointer", fontWeight: 600 }}>2026 사업자·과세기간 정보 {taxProfile.confirmed ? "(확인 완료)" : "(확인 필요)"}</summary>
            <p className="muted">입력한 값은 확인 완료 후 계산에 사용됩니다. 불명확한 거래는 자동으로 추정하지 않습니다.</p>
            <div className="form-field"><label className="form-field__label" htmlFor="entity-type">사업자 형태</label><select id="entity-type" className="input" value={taxProfile.entity_type ?? ""} onChange={(e) => updateProfile("entity_type", (e.target.value || null) as TaxProfileApi["entity_type"])}><option value="">선택</option><option value="individual">개인</option><option value="corporation">법인</option></select></div>
            <div className="form-field"><label className="form-field__label" htmlFor="industry-category">업종</label><select id="industry-category" className="input" value={taxProfile.industry_category ?? ""} onChange={(e) => updateProfile("industry_category", (e.target.value || null) as TaxProfileApi["industry_category"])}><option value="">선택</option><option value="food_service">음식점업</option><option value="manufacturing">제조업</option><option value="other">그 외 업종</option></select></div>
            {taxProfile.industry_category !== "other" && <div className="form-field"><label className="form-field__label" htmlFor="industry-subtype">세부 업종</label><select id="industry-subtype" className="input" value={taxProfile.industry_subtype ?? ""} onChange={(e) => updateProfile("industry_subtype", (e.target.value || null) as TaxProfileApi["industry_subtype"])}><option value="">선택</option>{taxProfile.industry_category === "food_service" ? <><option value="restaurant">일반 음식점</option><option value="taxable_entertainment">과세 유흥장소</option></> : <><option value="specified_mill">특정 제분업</option><option value="other">그 외 제조업</option></>}</select></div>}
            {taxProfile.industry_category === "manufacturing" && taxProfile.entity_type === "corporation" && <div className="form-field"><label className="form-field__label" htmlFor="sme-status">중소기업 여부</label><select id="sme-status" className="input" value={taxProfile.is_sme == null ? "" : String(taxProfile.is_sme)} onChange={(e) => updateProfile("is_sme", e.target.value === "" ? null : e.target.value === "true")}><option value="">확인 필요</option><option value="true">중소기업</option><option value="false">중소기업 아님</option></select></div>}
            <div className="field-row"><label htmlFor="sales-h1">2026년 1기 과세 매출액</label><input id="sales-h1" className="input" inputMode="numeric" value={taxProfile.taxable_sales_h1 ?? ""} onChange={(e) => updateProfile("taxable_sales_h1", e.target.value === "" ? null : Number(e.target.value.replace(/[^0-9]/g, "")))} /></div>
            <div className="field-row"><label htmlFor="sales-h2">2026년 2기 과세 매출액</label><input id="sales-h2" className="input" inputMode="numeric" value={taxProfile.taxable_sales_h2 ?? ""} onChange={(e) => updateProfile("taxable_sales_h2", e.target.value === "" ? null : Number(e.target.value.replace(/[^0-9]/g, "")))} /></div>
            {taxType === "general" && <>
              <p className="muted">의제매입 공제 한도에 쓰는 관련 매출액은 전체 과세 매출액과 다를 수 있습니다. 면세 원재료를 사용해 과세 공급한 금액을 확인해 입력하세요.</p>
              <div className="field-row"><label htmlFor="deemed-sales-h1">1기 의제매입 관련 과세 매출액</label><input id="deemed-sales-h1" className="input" inputMode="numeric" value={taxProfile.deemed_related_taxable_sales_h1 ?? ""} onChange={(e) => updateProfile("deemed_related_taxable_sales_h1", e.target.value === "" ? null : Number(e.target.value.replace(/[^0-9]/g, "")))} /></div>
              <div className="field-row"><label htmlFor="deemed-sales-h2">2기 의제매입 관련 과세 매출액</label><input id="deemed-sales-h2" className="input" inputMode="numeric" value={taxProfile.deemed_related_taxable_sales_h2 ?? ""} onChange={(e) => updateProfile("deemed_related_taxable_sales_h2", e.target.value === "" ? null : Number(e.target.value.replace(/[^0-9]/g, "")))} /></div>
            </>}
            {taxType === "simplified" && <div className="form-field"><label className="form-field__label" htmlFor="simplified-rate">간이과세 업종별 부가가치율 (국세청 확인값)</label><select id="simplified-rate" className="input" value={taxProfile.simplified_industry_rate ?? ""} onChange={(e) => updateProfile("simplified_industry_rate", e.target.value === "" ? null : Number(e.target.value))}><option value="">확인 필요</option>{[15, 20, 25, 30, 40].map((rate) => <option key={rate} value={rate}>{rate}%</option>)}</select></div>}
            <div className="field-row"><label htmlFor="business-start">개업일</label><input id="business-start" className="input" type="date" value={taxProfile.business_start_date ?? ""} onChange={(e) => updateProfile("business_start_date", e.target.value || null)} /></div>
            <div className="field-row"><label htmlFor="business-end">폐업일 (해당 시)</label><input id="business-end" className="input" type="date" value={taxProfile.business_end_date ?? ""} onChange={(e) => updateProfile("business_end_date", e.target.value || null)} /></div>
            <div className="field-row"><label htmlFor="tax-change-date">과세유형 변경일 (해당 시)</label><input id="tax-change-date" className="input" type="date" value={taxProfile.tax_type_change_date ?? ""} onChange={(e) => updateProfile("tax_type_change_date", e.target.value || null)} /></div>
            {taxProfile.tax_type_change_date && <div className="field-row"><label htmlFor="tax-change-to">변경 후 과세유형</label><select id="tax-change-to" className="input" value={taxProfile.changed_to_tax_type ?? ""} onChange={(e) => updateProfile("changed_to_tax_type", (e.target.value || null) as TaxProfileApi["changed_to_tax_type"])}><option value="">선택</option><option value="general">일반과세</option><option value="simplified">간이과세</option></select></div>}
            <div className="field-row"><label htmlFor="suspension-start">휴업 시작일 (해당 시)</label><input id="suspension-start" className="input" type="date" value={taxProfile.suspension_periods[0]?.start_date ?? ""} onChange={(e) => updateProfile("suspension_periods", e.target.value ? [{ start_date: e.target.value, end_date: taxProfile.suspension_periods[0]?.end_date ?? e.target.value }] : [])} /></div>
            <div className="field-row"><label htmlFor="suspension-end">휴업 종료일</label><input id="suspension-end" className="input" type="date" value={taxProfile.suspension_periods[0]?.end_date ?? ""} onChange={(e) => updateProfile("suspension_periods", e.target.value ? [{ start_date: taxProfile.suspension_periods[0]?.start_date ?? e.target.value, end_date: e.target.value }] : [])} /></div>
            <div className="btn-row"><button className="btn btn--secondary" disabled={profileSaving} onClick={() => void saveProfile(false)}>저장</button><button className="btn btn--primary" disabled={profileSaving} onClick={() => void saveProfile(true)}>정보 확인 완료</button></div>
          </details>
        )}
        {message && <div className="banner banner--info" role="status" style={{ marginBottom: 12 }}>{message}</div>}
        {receiptInbox.length > 0 && (
          <section style={{ marginBottom: 20 }}>
            <h2 style={{ fontSize: 18 }}>거래 정보 확인이 필요해요</h2>
            <p className="muted">추출 결과 확인은 끝났습니다. 보관함에서 거래 정보를 검토·저장한 뒤 별도로 분석할 수 있습니다.</p>
            {receiptInbox.map((receipt) => (
              <article key={receipt.id} className="card" style={{ marginBottom: 10 }}>
                <strong>{receipt.vendor ?? "거래처 확인 필요"}</strong>
                <div className="muted">{receipt.date ?? "거래일 확인 필요"} · {receipt.amount?.toLocaleString("ko-KR") ?? "금액 확인 필요"}원</div>
                {receipt.ocr_warnings.map((warning) => <p className="muted" key={warning}>{warning}</p>)}
                <button className="btn btn--secondary" style={{ marginTop: 10 }} onClick={() => navigate(`/receipts/${receipt.id}/edit`)}>
                  거래 정보 확인·저장
                </button>
              </article>
            ))}
          </section>
        )}
        <div className="btn-row" style={{ marginBottom: 16 }}>
          {purchase && <button className="btn btn--primary" disabled={busy || selected.length === 0} onClick={() => void analyzeSelected()}>
            {busy ? "분석 준비 중" : `선택 거래 분석하기 (${selected.length})`}
          </button>}
          <button className="btn btn--secondary" onClick={() => navigate(`/storage/trash?direction=${direction}`)}>휴지통</button>
          <button className="btn btn--secondary" onClick={() => void refresh()} disabled={loading}>새로고침</button>
        </div>
        <div className="vault-filters"><label>거래 월<input className="input" type="month" value={month} onChange={(event) => setMonth(event.target.value)} /></label><label>정렬<select className="input" value={order} onChange={(event) => setOrder(event.target.value)}><option value="newest">최신순</option><option value="oldest">오래된순</option><option value="amount">금액순</option></select></label></div>
        {purchase && <label className="form-field">분석 상태<select className="input" value={status} onChange={(event) => setStatus(event.target.value)}><option value="all">전체</option>{Object.entries(statusLabels).filter(([key]) => key !== "pending").map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>}
        <div className="field-row"><span className="muted">{filtered.length}건</span><button onClick={() => { setMonth(""); setStatus("all"); }}>필터 초기화</button></div>
        {loading && <div className="center-note">거래를 불러오는 중입니다.</div>}
        {!loading && filtered.length === 0 && <div className="center-note">표시할 거래가 없습니다. 증빙을 등록하거나 필터를 변경해 주세요.</div>}
        {filtered.map((item) => (
          <article key={item.id} className="card transaction-row">
            {purchase && <input
              type="checkbox"
              aria-label={`${item.vendor} 분석 선택`}
              checked={selected.includes(item.id)}
              disabled={item.state !== "confirmed" || item.review_status === "analyzed"}
              onChange={(event) => setSelected((current) => event.target.checked ? [...current, item.id] : current.filter((id) => id !== item.id))}
            />}
            <div className="transaction-row__body">
              <strong>{item.description || item.vendor}</strong>
              <div className="muted">{item.transaction_date} · {item.vendor}</div>
              <strong>{fmt.won(item.total_amount)}</strong>
              <div className="pill pill--muted">{purchase ? statusLabels[item.review_status] ?? "확인 필요" : item.state === "confirmed" ? "확인 완료" : "확인 전"}</div>
            </div>
            <button className="row-delete" onClick={() => { setDeleteError(""); setDeleteTarget(item); }}>삭제</button>
          </article>
        ))}
      </div>
      {deleteTarget && <DeleteConfirmation name={deleteTarget.description || deleteTarget.vendor} busy={deleting} error={deleteError} onCancel={() => setDeleteTarget(null)} onConfirm={() => void removeTransaction(deleteTarget.id)} />}
    </div>
  );
}
