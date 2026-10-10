import { useEffect, useState } from "react";
import { isAxiosError } from "axios";
import { useNavigate, useParams } from "react-router-dom";
import { getReceipt } from "../../api/receipts";
import { confirmTransaction, createTransactionFromReceipt } from "../../api/transactions";
import { PageHeader } from "../../components/PageHeader";

export function OcrResultEditPage() {
  const navigate = useNavigate();
  const { id } = useParams();
  const [vendor, setVendor] = useState("");
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [transactionDate, setTransactionDate] = useState("");
  const [taxTreatment, setTaxTreatment] = useState<"standard" | "exempt">("standard");
  const [evidenceType, setEvidenceType] = useState<"tax_invoice" | "card_receipt" | "cash_receipt" | "tax_free_receipt" | "unknown">("unknown");
  const [businessRelated, setBusinessRelated] = useState<"yes" | "no" | "unknown">("unknown");
  const [deemedInput, setDeemedInput] = useState(false);
  const [deemedDocument, setDeemedDocument] = useState<"purchase_invoice" | "card_statement" | "farmer_direct" | "import_declaration">("farmer_direct");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!id) return;
    getReceipt(Number(id))
      .then((receipt) => {
        if (receipt.status !== "done") throw new Error("OCR에 성공한 영수증만 거래로 확정할 수 있습니다.");
        setVendor(receipt.vendor ?? "");
        setDescription(receipt.ocr_raw ?? "");
        setAmount(receipt.amount == null ? "" : String(Math.round(receipt.amount)));
        setTransactionDate(receipt.date ?? "");
      })
      .catch((cause) => setError(cause instanceof Error ? cause.message : "영수증 정보를 불러오지 못했습니다."))
      .finally(() => setLoading(false));
  }, [id]);

  async function saveConfirmedTransaction() {
    if (!id || !vendor.trim() || !transactionDate || !amount || Number(amount) < 0) {
      setError("거래처, 거래일, 총액을 확인해 주세요.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const total = Math.round(Number(amount));
      const supply = taxTreatment === "exempt" ? total : Math.round(total / 1.1);
      const vat = taxTreatment === "exempt" ? 0 : total - supply;
      const transaction = await createTransactionFromReceipt(Number(id), {
        direction: "purchase",
        transaction_date: transactionDate,
        vendor: vendor.trim(),
        description,
        evidence_type: taxTreatment === "exempt" ? "tax_free_receipt" : evidenceType,
        business_related: businessRelated === "unknown" ? null : businessRelated === "yes",
        total_amount: total,
        supply_amount: supply,
        vat_amount: vat,
        deemed_input_supply: deemedInput ? supply : 0,
        deemed_input_eligible: deemedInput,
        deemed_input_document_type: deemedInput ? deemedDocument : null,
        tax_treatment: taxTreatment,
      });
      await confirmTransaction(transaction.id);
      navigate("/dashboard", { state: { transactionSaved: true } });
    } catch (cause) {
      setError(isAxiosError(cause) ? cause.response?.data?.error?.message ?? "거래를 저장하지 못했습니다." : "거래를 저장하지 못했습니다.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="page">
      <PageHeader title="추출 거래 확인" showAmountToggle />
      <div className="page__body">
        <div className="banner banner--warning" style={{ marginBottom: 20 }}>
          <span>⚠️</span>
          <div>OCR 추출 내용을 원본 증빙과 대조해 주세요. 이 화면은 공제액을 계산하거나 반영하지 않습니다.</div>
        </div>
        {error && <div className="banner banner--error" role="alert">{error}</div>}
        {loading ? <div className="center-note">OCR 결과를 불러오는 중입니다.</div> : (
          <>
            <div className="form-field">
              <label className="form-field__label" htmlFor="transaction-vendor">거래처</label>
              <input id="transaction-vendor" className="input" value={vendor} onChange={(e) => setVendor(e.target.value)} />
            </div>
            <div className="form-field">
              <label className="form-field__label" htmlFor="transaction-description">거래 내용</label>
              <input id="transaction-description" className="input" value={description} onChange={(e) => setDescription(e.target.value)} />
            </div>
            <div className="form-field">
              <label className="form-field__label" htmlFor="transaction-total">거래 총액 (원)</label>
              <input id="transaction-total" className="input" inputMode="numeric" value={amount} onChange={(e) => setAmount(e.target.value.replace(/[^0-9]/g, ""))} />
            </div>
            <div className="form-field">
              <label className="form-field__label" htmlFor="transaction-date">거래일</label>
              <input id="transaction-date" className="input" type="date" value={transactionDate} onChange={(e) => setTransactionDate(e.target.value)} />
            </div>
            <div className="form-field">
              <label className="form-field__label" htmlFor="tax-treatment">증빙 과세 구분</label>
              <select id="tax-treatment" className="input" value={taxTreatment} onChange={(e) => { const value = e.target.value as "standard" | "exempt"; setTaxTreatment(value); if (value !== "exempt") setDeemedInput(false); }}>
                <option value="standard">과세 거래 (세금계산서상 세액 확인 필요)</option>
                <option value="exempt">면세 거래</option>
              </select>
            </div>
            <div className="form-field">
              <label className="form-field__label" htmlFor="evidence-type">거래 증빙</label>
              <select id="evidence-type" className="input" value={evidenceType} onChange={(e) => setEvidenceType(e.target.value as typeof evidenceType)}>
                <option value="unknown">증빙 유형 확인 필요</option><option value="tax_invoice">세금계산서</option><option value="card_receipt">사업용 신용카드</option><option value="cash_receipt">현금영수증</option><option value="tax_free_receipt">면세 계산서·영수증</option>
              </select>
            </div>
            <div className="form-field">
              <label className="form-field__label" htmlFor="business-related">사업 관련 지출인가요?</label>
              <select id="business-related" className="input" value={businessRelated} onChange={(e) => setBusinessRelated(e.target.value as "yes" | "no" | "unknown")}>
                <option value="unknown">아직 확인하지 않음</option>
                <option value="yes">예</option>
                <option value="no">아니요</option>
              </select>
            </div>
            {taxTreatment === "exempt" && <section className="card" style={{ marginTop: 12 }}>
              <label style={{ display: "flex", gap: 8, alignItems: "flex-start" }}><input type="checkbox" checked={deemedInput} onChange={(e) => setDeemedInput(e.target.checked)} /><span>면세 농·축·수산물 등을 과세사업에 사용했고, 의제매입세액공제 대상 사실을 확인했습니다.</span></label>
              {deemedInput && <div className="form-field" style={{ marginTop: 12 }}><label className="form-field__label" htmlFor="deemed-document">구비 증빙 유형</label><select id="deemed-document" className="input" value={deemedDocument} onChange={(e) => setDeemedDocument(e.target.value as typeof deemedDocument)}><option value="farmer_direct">생산자 직접 구입 증빙</option><option value="purchase_invoice">매입처별 계산서 합계표 등</option><option value="card_statement">카드·현금영수증 등 매입 증빙</option><option value="import_declaration">수입 신고 증빙</option></select><p className="muted">이 선택만으로 공제가 확정되지는 않습니다. 분석 및 업종·한도 확인 전까지 예상 공제액에서 제외됩니다.</p></div>}
            </section>}
            <p>저장한 매입 거래는 보관함에서 선택해 분석할 수 있습니다. 정보가 부족한 거래는 공제액 계산에서 제외됩니다.</p>
            <div className="stack-gap-sm" style={{ marginTop: 24 }}>
              <button className="btn btn--primary" disabled={saving} onClick={() => void saveConfirmedTransaction()}>
                {saving ? "저장 중" : "거래 확정 및 보관함에 저장"}
              </button>
              <button className="btn btn--secondary" onClick={() => navigate("/capture")}>다시 촬영하기</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
