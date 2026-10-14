import { useEffect, useState } from "react";
import { isAxiosError } from "axios";
import { useNavigate, useParams } from "react-router-dom";
import { confirmReceiptExtraction, getReceipt, type ReceiptProcessingApi, type ReceiptDetails } from "../../api/receipts";
import { PageHeader } from "../../components/PageHeader";
import { ReceiptPreview } from "../../components/ReceiptPreview";

import { ReceiptDetailsForm } from "../../components/ReceiptDetailsForm";

const fieldLabels: Record<string, string> = {
  vendor: "거래처",
  amount: "거래 금액",
  transaction_date: "거래일",
};

export function OcrExtractionReviewPage() {
  const navigate = useNavigate();
  const { id } = useParams();
  const [receipt, setReceipt] = useState<ReceiptProcessingApi | null>(null);
  const [details,setDetails] = useState<ReceiptDetails>({});
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
        setDetails(result.details ?? {});
        setVendor(result.vendor ?? "");
        setAmount(result.amount == null ? "" : String(Math.round(result.amount)));
        setDate(result.date ?? "");
      })
      .catch((cause) => setError(cause instanceof Error ? cause.message : "추출 결과를 불러오지 못했습니다."))
      .finally(() => setLoading(false));
  }, [id]);

  async function confirmAndOpenVault(destination: "vault" | "home" | "capture" = "vault") {
    if (!id || !vendor.trim() || amount === "" || !date || Number(amount) < 0) {
      setError("거래처, 거래 금액, 거래일을 확인해 주세요.");
      return;
    }
    if (details.items?.some(item => !item.name.trim()) || details.additional_fields?.some(item => !item.label.trim())) {
      setError("추가한 품목명과 항목명을 입력해 주세요. 필요 없는 행은 삭제해 주세요.");
      return;
    }
    const money = [details.supply_amount, details.vat_amount, details.tax_free_amount,
      ...(details.items ?? []).flatMap(item => [item.unit_price, item.amount])];
    if (money.some(value => value != null && (!Number.isSafeInteger(value) || value < 0)) ||
      details.items?.some(item => item.quantity != null && (!Number.isFinite(item.quantity) || item.quantity < 0))) {
      setError("금액은 0 이상의 정수, 수량은 0 이상의 숫자로 입력해 주세요.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await confirmReceiptExtraction(Number(id), { vendor: vendor.trim(), amount: Math.round(Number(amount)), date, details });
      navigate(destination === "home" ? "/dashboard" : destination === "capture" ? `/capture?direction=${receipt?.direction ?? "purchase"}` : `/storage/${receipt?.direction ?? "purchase"}`, { replace: true });
    } catch (cause) {
      setError(isAxiosError(cause) ? cause.response?.data?.error?.message ?? "추출 결과를 저장하지 못했습니다." : "추출 결과를 저장하지 못했습니다.");
    } finally {
      setSaving(false);
    }
  }

  const fields = receipt ? [
    { key: "vendor", value: receipt.vendor, label: "거래처" },
    { key: "amount", value: receipt.amount, label: "거래 금액" },
    { key: "transaction_date", value: receipt.date, label: "거래일" },
  ] : [];
  const missing = fields.filter(field => field.value == null || field.value === "" || receipt?.ocr_missing_fields.includes(field.key));
  const missingNames = missing.map(field => fieldLabels[field.key]).join(", ");
  return (
    <div className="page qa-page">
      <PageHeader title="추출 결과 확인" showAmountToggle onBack={() => navigate(`/storage/${receipt?.direction ?? "purchase"}`)} />
      <div className="page__body">
        <div className="banner banner--info" style={{ marginBottom: 16 }}>
          인식한 내용을 원본 증빙과 대조해 주세요. 확인 후 선택한 보관함으로 이동하며, 거래 확정과 공제 분석은 별도로 진행됩니다.
        </div>
        {error && <div className="banner banner--error" role="alert">{error}</div>}
        {loading ? <div className="center-note">추출 결과를 불러오는 중입니다.</div> : receipt && <>
          <ReceiptPreview id={receipt.id} />
          <div className="extraction-status" aria-label="추출 항목 상태">{fields.map(field => <span key={field.key} className={missing.some(item => item.key === field.key) ? "status-label--review" : "status-label--done"}>{field.label} · {receipt.extraction_confirmed ? "확인 완료" : missing.some(item => item.key === field.key) ? "직접 입력 필요" : "추출됨"}</span>)}</div>
          {missing.length > 0 ? <div className="banner banner--warning" style={{ marginBottom: 16 }}>필수항목 {missing.length}개를 추출하지 못했습니다. 원본을 보고 다음 항목을 직접 입력해 주세요: {missingNames}.</div> : <p className="banner banner--info">{receipt.extraction_confirmed ? "이전에 확인한 내용입니다." : "필수항목 3개를 추출했습니다."} 원본과 비교하고 잘못된 값은 수정해 주세요.</p>}
          {!!receipt.ocr_warnings.length && <details className="ocr-notes"><summary>인식 과정 안내</summary>{receipt.ocr_warnings.map(warning => <p className="muted" key={warning}>{warning}</p>)}</details>}
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
          <ReceiptDetailsForm value={details} original={receipt.details??{}} confirmed={receipt.extraction_confirmed} onChange={setDetails}/>
          <button className="btn btn--primary" style={{ width: "100%", marginTop: 20 }} disabled={saving} onClick={() => void confirmAndOpenVault()}>
            {saving ? "확인 내용을 저장 중" : "확인 후 보관함으로 이동"}
          </button>
          <button className="btn btn--ghost" style={{ marginTop: 10 }} disabled={saving} onClick={() => void confirmAndOpenVault("home")}>확인 후 메인으로 이동</button>
          <div className="ocr-secondary-actions"><button className="text-link" disabled={saving} onClick={() => navigate(`/capture?direction=${receipt.direction}`)}>재촬영</button><button className="text-link" disabled={saving} onClick={() => void confirmAndOpenVault("capture")}>저장 후 다른 사진 추가 촬영·첨부</button></div>
          <p className="footnote">재촬영 시 현재 입력한 수정값은 저장되지 않습니다.</p>
        </>}
      </div>
    </div>
  );
}
