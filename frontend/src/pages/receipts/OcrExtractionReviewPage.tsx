import { useEffect, useState } from "react";
import { isAxiosError } from "axios";
import { useNavigate, useParams } from "react-router-dom";
import { confirmReceiptExtraction, getReceipt, type ReceiptProcessingApi } from "../../api/receipts";
import { PageHeader } from "../../components/PageHeader";

const fieldLabels: Record<string, string> = {
  vendor: "거래처",
  amount: "거래 금액",
  transaction_date: "거래일",
};

export function OcrExtractionReviewPage() {
  const navigate = useNavigate();
  const { id } = useParams();
  const [receipt, setReceipt] = useState<ReceiptProcessingApi | null>(null);
  const [vendor, setVendor] = useState("");
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!id) return;
    getReceipt(Number(id))
      .then((result) => {
        if (result.status !== "done") throw new Error("OCR가 완료된 증빙만 확인할 수 있습니다.");
        setReceipt(result);
        setVendor(result.vendor ?? "");
        setAmount(result.amount == null ? "" : String(Math.round(result.amount)));
        setDate(result.date ?? "");
      })
      .catch((cause) => setError(cause instanceof Error ? cause.message : "추출 결과를 불러오지 못했습니다."))
      .finally(() => setLoading(false));
  }, [id]);

  async function confirmAndOpenVault() {
    if (!id || !vendor.trim() || amount === "" || !date || Number(amount) < 0) {
      setError("거래처, 거래 금액, 거래일을 확인해 주세요.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await confirmReceiptExtraction(Number(id), { vendor: vendor.trim(), amount: Math.round(Number(amount)), date });
      navigate("/storage/purchase", { replace: true });
    } catch (cause) {
      setError(isAxiosError(cause) ? cause.response?.data?.error?.message ?? "추출 결과를 저장하지 못했습니다." : "추출 결과를 저장하지 못했습니다.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="page">
      <PageHeader title="추출 결과 확인" showAmountToggle />
      <div className="page__body">
        <div className="banner banner--info" style={{ marginBottom: 16 }}>
          인식한 내용을 원본 증빙과 대조해 주세요. 확인을 누르면 매입 보관함으로 이동하며, 거래 확정과 공제 분석은 별도로 진행됩니다.
        </div>
        {error && <div className="banner banner--error" role="alert">{error}</div>}
        {loading ? <div className="center-note">추출 결과를 불러오는 중입니다.</div> : receipt && <>
          {receipt.ocr_missing_fields.length > 0 && <div className="banner banner--warning" style={{ marginBottom: 16 }}>
            확인하거나 입력할 항목: {receipt.ocr_missing_fields.map((field) => fieldLabels[field] ?? field).join(", ")}
          </div>}
          {receipt.ocr_warnings.map((warning) => <div className="banner banner--warning" style={{ marginBottom: 12 }} key={warning}>{warning}</div>)}
          {receipt.ocr_raw && <details className="card" style={{ marginBottom: 16 }}>
            <summary style={{ cursor: "pointer", fontWeight: 700 }}>인식된 원문 보기</summary>
            <pre style={{ whiteSpace: "pre-wrap", fontFamily: "inherit", marginBottom: 0 }}>{receipt.ocr_raw}</pre>
          </details>}
          <div className="form-field">
            <label className="form-field__label" htmlFor="ocr-review-vendor">거래처</label>
            <input id="ocr-review-vendor" className="input" value={vendor} onChange={(event) => setVendor(event.target.value)} />
          </div>
          <div className="form-field">
            <label className="form-field__label" htmlFor="ocr-review-amount">거래 금액 (원)</label>
            <input id="ocr-review-amount" className="input" inputMode="numeric" value={amount} onChange={(event) => setAmount(event.target.value.replace(/[^0-9]/g, ""))} />
          </div>
          <div className="form-field">
            <label className="form-field__label" htmlFor="ocr-review-date">거래일</label>
            <input id="ocr-review-date" className="input" type="date" value={date} onChange={(event) => setDate(event.target.value)} />
          </div>
          <button className="btn btn--primary" style={{ width: "100%", marginTop: 20 }} disabled={saving} onClick={() => void confirmAndOpenVault()}>
            {saving ? "확인 내용을 저장 중" : "확인하고 매입 보관함으로"}
          </button>
        </>}
      </div>
    </div>
  );
}
