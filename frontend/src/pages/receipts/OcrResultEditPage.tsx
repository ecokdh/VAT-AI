import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { isAxiosError } from "axios";
import { ReceiptReview, type ItemDraft } from "../../components/ReceiptReview";
import { DiscountEditor, type DiscountDraft } from "../../components/DiscountEditor";
import { PageHeader } from "../../components/PageHeader";
import {
  confirmReceiptOcr,
  getReceipt,
  updateReceiptOcr,
  type ReceiptApi,
  type DocumentFacts,
  type StructuredItem,
  type Evidence,
} from "../../api/receipts";

function itemDraft(item: StructuredItem): ItemDraft {
  return { ...item, key: item.id ?? crypto.randomUUID(), quantity: String(item.quantity ?? ""),
    printed_unit_price: String(item.printed_unit_price ?? ""), line_amount: String(item.line_amount ?? ""),
    discount_amount: String(item.discount_amount ?? "") };
}

function numberText(value: number | null | undefined): string {
  if (value === null || value === undefined) return "";
  return String(value);
}

function parseNumber(value: string, label: string, signed = false): number | null {
  const trimmed = value.replace(/,/g, "").trim();
  if (!trimmed) return null;
  if (!(signed ? /^-?\d+(\.\d+)?$/ : /^\d+(\.\d+)?$/).test(trimmed)) {
    throw new Error(`${label}은 숫자만 입력하세요.`);
  }
  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed) || (!signed && parsed < 0)) {
    throw new Error(`${label}은 0 이상이어야 합니다.`);
  }
  return parsed;
}

function originalSnapshot(raw: string | null | undefined): Record<string, unknown> | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

export function OcrResultEditPage() {
  const navigate = useNavigate();
  const { id } = useParams();
  const [receipt, setReceipt] = useState<ReceiptApi | null>(null);
  const [vendor, setVendor] = useState("");
  const [businessNumber, setBusinessNumber] = useState("");
  const [rows, setRows] = useState<ItemDraft[]>([]);
  const [document, setDocument] = useState<DocumentFacts>({ document_type: "UNKNOWN" });
  const [fieldStates, setFieldStates] = useState<Record<string, Evidence["state"]>>({});
  const [discounts, setDiscounts] = useState<DiscountDraft[]>([]);
  const [supplyAmount, setSupplyAmount] = useState("");
  const [vatAmount, setVatAmount] = useState("");
  const [amount, setAmount] = useState("");
  const [separated, setSeparated] = useState(false);
  const [taxable, setTaxable] = useState("");
  const [exempt, setExempt] = useState("");
  const [transaction, setTransaction] = useState("");
  const [payment, setPayment] = useState("");
  const [subtotal, setSubtotal] = useState("");
  const [issuedAt, setIssuedAt] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [ready, setReady] = useState(false);
  const [needsRefresh, setNeedsRefresh] = useState(false);
  const [baseMoney, setBaseMoney] = useState<{
    amount: number | null;
    supply: number | null;
    vat: number | null;
    taxable: number | null;
    exempt: number | null;
    transaction: number | null;
    payment: number | null;
    subtotal: number | null;
  }>({ amount: null, supply: null, vat: null, taxable: null, exempt: null, transaction: null, payment: null, subtotal: null });

  function fillForm(data: ReceiptApi) {
    setReceipt(data);
    setFieldStates({});
    setVendor(data.vendor ?? "");
    setBusinessNumber(data.business_number ?? "");
    setRows((data.line_items ?? []).map(itemDraft));
    setDocument(data.document ?? { document_type: "UNKNOWN" });
    setDiscounts((data.document?.discounts ?? []).map(discount => ({ ...discount, amount: String(discount.amount) })));
    setSupplyAmount(numberText(data.supply_amount));
    setVatAmount(numberText(data.vat_amount));
    setAmount(numberText(data.amount));
    setIssuedAt(data.date ?? "");
    setSeparated(data.money_schema_version === 2 || [data.taxable_supply_amount, data.tax_exempt_amount, data.transaction_amount, data.payment_amount, data.subtotal_amount].some(value => value != null));
    setTaxable(numberText(data.taxable_supply_amount));
    setExempt(numberText(data.tax_exempt_amount));
    setTransaction(numberText(data.transaction_amount));
    setPayment(numberText(data.payment_amount));
    setSubtotal(numberText(data.subtotal_amount));
    setBaseMoney({
      amount: data.amount ?? null,
      supply: data.supply_amount ?? null,
      vat: data.vat_amount ?? null,
      taxable: data.taxable_supply_amount ?? null,
      exempt: data.tax_exempt_amount ?? null,
      transaction: data.transaction_amount ?? null,
      payment: data.payment_amount ?? null,
      subtotal: data.subtotal_amount ?? null,
    });
  }

  async function reloadReceipt() {
    if (!id) return;
    const data = await getReceipt(Number(id));
    if (data.status === "retake") {
      navigate("/capture", { replace: true });
      return;
    }
    fillForm(data);
    setReady(true);
    setNeedsRefresh(false);
  }

  async function handleReload() {
    if (saving) return;
    setSaving(true);
    try {
      await reloadReceipt();
      setError("");
    } catch {
      setError("최신 값을 불러오지 못했습니다. 입력은 유지됩니다. 다시 불러오세요.");
    } finally {
      setSaving(false);
    }
  }

  useEffect(() => {
    if (!id) return;
    let active = true;
    getReceipt(Number(id))
      .then((data) => {
        if (!active) return;
        if (data.status === "retake") {
          navigate("/capture", { replace: true });
          return;
        }
        fillForm(data);
        setReady(true);
      })
      .catch((requestError) => {
        if (!active) return;
        const message = isAxiosError(requestError)
          ? requestError.response?.data?.error?.message
          : undefined;
        setError(message ?? "영수증을 불러오지 못했습니다.");
      });
    return () => {
      active = false;
    };
  }, [id, navigate]);

  const original = useMemo(() => originalSnapshot(receipt?.ocr_original), [receipt]);
  const inputDisabled = !ready || saving || needsRefresh || Boolean(receipt?.confirmed);

  function editValue(key: string, value: string, setter: (value: string) => void) {
    setter(value);
    setFieldStates(current => ({ ...current, [key]: value.trim() ? "READ" : "UNREVIEWED" }));
  }

  function editDocumentValue(key: string, value: string) {
    setDocument(current => ({ ...current, [key]: value || null, sources: {
      ...current.sources, [key]: { kind: "manual", state: value.trim() ? "READ" : "UNREVIEWED",
        boxes: current.sources?.[key]?.boxes ?? [], confidence: null },
    } }));
  }

  function stateControl(key: string, label: string, value: string, setter: (value: string) => void, documentField = false) {
    const source = documentField ? document.sources?.[key] : receipt?.money_sources?.[key] ?? receipt?.document.sources?.[key];
    const state = documentField ? source?.state ?? (value ? "READ" : "UNREVIEWED")
      : fieldStates[key] ?? source?.state ?? (value ? "READ" : "UNREVIEWED");
    const manual = documentField ? source?.kind === "manual" : fieldStates[key] !== undefined || source?.kind === "manual";
    return <><select className="input" aria-label={`${label} 값 상태`} disabled={inputDisabled} value={state}
      onChange={event => {
        const next = event.target.value as Evidence["state"];
        if (["ABSENT", "FAILED", "NOT_APPLICABLE"].includes(next)) setter("");
        if (documentField) setDocument(current => ({ ...current, sources: { ...current.sources,
          [key]: { kind: "manual", state: next, boxes: current.sources?.[key]?.boxes ?? [], confidence: null } } }));
        else setFieldStates(current => ({ ...current, [key]: next }));
      }}>
      {value && <option value="READ">읽음</option>}
      <option value="UNREVIEWED">미확인</option><option value="ABSENT">실제 미기재</option>
      <option value="FAILED">판독 실패</option><option value="NOT_APPLICABLE">해당 없음</option>
    </select>
      {source && <small className="muted">출처: {manual ? "사용자 수정" : source.kind === "calculated" ? "계산" : "OCR"}
        {!manual && source.confidence != null ? ` · 인식 신뢰도 ${Math.round(source.confidence * 100)}%` : ""}</small>}
    </>;
  }

  async function handleConfirm(confirmAfterSave = true) {
    if (!id || !ready || !receipt || saving || needsRefresh || receipt.confirmed) return;
    setError("");
    setSaving(true);
    let stage: "save" | "confirm" = "save";
    try {
      const structured = rows.map(row => {
        const { key, ...item } = row;
        void key;
        if (!row.name.trim()) throw new Error("품목명을 입력하거나 빈 품목을 삭제하세요.");
        return { ...item, name: row.name.trim(), quantity: parseNumber(row.quantity, `${row.name} 수량`, true),
          printed_unit_price: parseNumber(row.printed_unit_price, `${row.name} 인쇄 단가`),
          line_amount: parseNumber(row.line_amount, `${row.name} 행 금액`, true),
          discount_amount: parseNumber(row.discount_amount, `${row.name} 할인`) };
      });
      const saved = await updateReceiptOcr(Number(id), {
        field_states: fieldStates,
        base_revision: receipt.revision,
        vendor: vendor.trim() || null,
        business_number: businessNumber.replace(/\D/g, "") || null,
        line_items: structured,
        document: { ...document, discounts: discounts.map((discount, index) => {
          const value = parseNumber(discount.amount, `할인 ${index + 1} 금액`);
          if (value === null) throw new Error(`할인 ${index + 1} 금액을 입력하세요.`);
          return { ...discount, amount: value };
        }) },
        ...(separated ? {
          taxable_supply_amount: parseNumber(taxable, "과세 공급가액", Boolean(document.adjustment_type)),
          tax_exempt_amount: parseNumber(exempt, "면세 금액", Boolean(document.adjustment_type)),
          transaction_amount: parseNumber(transaction, "거래 총액", Boolean(document.adjustment_type)),
          payment_amount: parseNumber(payment, "결제금액", Boolean(document.adjustment_type)),
          subtotal_amount: parseNumber(subtotal, "할인 전 합계", Boolean(document.adjustment_type)),
        } : { supply_amount: parseNumber(supplyAmount, "공급가액", Boolean(document.adjustment_type)), amount: parseNumber(amount, "총액", Boolean(document.adjustment_type)) }),
        vat_amount: parseNumber(vatAmount, "부가세", Boolean(document.adjustment_type)),
        date: issuedAt || null,
        base_amount: baseMoney.amount,
        base_supply_amount: baseMoney.supply,
        base_vat_amount: baseMoney.vat,
        base_taxable_supply_amount: baseMoney.taxable,
        base_tax_exempt_amount: baseMoney.exempt,
        base_transaction_amount: baseMoney.transaction,
        base_payment_amount: baseMoney.payment,
        base_subtotal_amount: baseMoney.subtotal,
      });
      fillForm(saved);
      if (!confirmAfterSave) return;
      stage = "confirm";
      await confirmReceiptOcr(Number(id), saved.revision);
      navigate("/storage/purchase", { replace: true });
    } catch (requestError) {
      const message = isAxiosError(requestError)
        ? requestError.response?.data?.error?.message
        : undefined;
      const conflict = isAxiosError(requestError)
        && requestError.response?.status === 409
        && requestError.response?.data?.error?.code === "DATA_CONFLICT";
      const uncertainConfirm = stage === "confirm" && isAxiosError(requestError)
        && (!requestError.response || requestError.response.status >= 500);
      if (conflict) {
        const conflictMessage = message ?? "서버 값이 바뀌었습니다. 다시 확인하세요.";
        setError(conflictMessage);
        setNeedsRefresh(true);
        try {
          await reloadReceipt();
        } catch {
          setError(`${conflictMessage} 최신 값을 불러오지 못했습니다. 다시 불러온 뒤 확인하세요.`);
        }
      } else if (uncertainConfirm) {
        setNeedsRefresh(true);
        setError("확정 결과를 확인하지 못했습니다. 서버에서 확정됐을 수 있으니 최신 상태를 다시 불러오세요.");
      } else {
        setError(requestError instanceof Error && !isAxiosError(requestError)
          ? requestError.message
          : message ?? (stage === "save"
            ? "수정 내용을 저장하지 못했습니다. 입력은 유지됩니다. 다시 시도하세요."
            : "확정하지 못했습니다. 칸을 확인하세요."));
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="page">
      <PageHeader title="추출 결과 확인 및 수정" showAmountToggle />
      <div className="page__body">
        <div className="banner banner--warning" style={{ marginBottom: 20 }}>
          <span>⚠️</span>
          <div>읽은 값이 틀릴 수 있습니다. 실물과 대조한 뒤 확정하세요. 처음 읽은 값은 덮이지 않습니다.</div>
        </div>

        {original && (
          <div className="muted" style={{ fontSize: 13, marginBottom: 16 }}>
            처음 읽은 값: {String(original.vendor ?? "-")} / {String(original.amount ?? "-")} /{" "}
            {String(original.date ?? "-")}
          </div>
        )}

        <div className="form-field">
          <label className="form-field__label">상호</label>
          <input className="input" value={vendor} disabled={inputDisabled} onChange={(e) => editValue("vendor", e.target.value, setVendor)} />
          {stateControl("vendor", "상호", vendor, setVendor)}
        </div>
        <div className="form-field">
          <label className="form-field__label">사업자등록번호</label>
          <input className="input" disabled={inputDisabled} value={businessNumber} onChange={(e) => editValue("business_number", e.target.value, setBusinessNumber)} />
          {stateControl("business_number", "사업자등록번호", businessNumber, setBusinessNumber)}
        </div>
        {id && <ReceiptReview receiptId={Number(id)} rows={rows} onChange={setRows} disabled={inputDisabled} />}
        <DiscountEditor discounts={discounts} items={rows} onChange={setDiscounts} disabled={inputDisabled} />
        <div className="form-field">
          <label className="form-field__label" htmlFor="document-type">증빙 종류</label>
          <select id="document-type" className="input" disabled={inputDisabled} value={document.document_type}
            onChange={e => setDocument(current => ({ ...current, document_type: e.target.value as DocumentFacts["document_type"] }))}>
            <option value="UNKNOWN">기타·미확인</option><option value="CARD_RECEIPT">카드전표</option>
            <option value="CASH_RECEIPT">현금영수증</option><option value="GENERAL_RECEIPT">일반 영수증</option>
            <option value="TAX_INVOICE">세금계산서</option><option value="INVOICE">계산서</option>
          </select>
          <small className="muted">세금계산서·계산서는 전용 자동 추출을 지원하지 않습니다.</small>
        </div>
        {([ ["supply_date", "공급일"], ["document_issue_date", "발행일"], ["payment_date", "결제일"] ] as const).map(([key, label]) => <div className="form-field" key={key}>
          <label className="form-field__label" htmlFor={key}>{label}</label>
          <input id={key} className="input" type="date" disabled={inputDisabled} value={document[key] ?? ""}
            onChange={e => editDocumentValue(key, e.target.value)} />
          {stateControl(key, label, document[key] ?? "", value => editDocumentValue(key, value), true)}
        </div>)}
        <div className="form-field">
          <label className="form-field__label" htmlFor="adjustment-type">거래 구분</label>
          <select id="adjustment-type" className="input" disabled={inputDisabled} value={document.adjustment_type ?? ""}
            onChange={e => setDocument(current => ({ ...current, adjustment_type: (e.target.value || null) as DocumentFacts["adjustment_type"] }))}>
            <option value="">일반 거래</option><option value="RETURN">반품</option>
            <option value="CANCELLATION">취소</option><option value="CORRECTION">금액 조정</option>
          </select>
          {document.adjustment_type && <small className="muted">반품·취소 금액은 음수 그대로 입력하세요. 원거래는 확정 후 연결할 수 있습니다.</small>}
        </div>
        <div className="form-field">
          <label className="form-field__label" htmlFor="approval-number">승인번호</label>
          <input id="approval-number" className="input" disabled={inputDisabled} value={document.approval_number ?? ""}
            onChange={e => editDocumentValue("approval_number", e.target.value)} />
          {stateControl("approval_number", "승인번호", document.approval_number ?? "", value => editDocumentValue("approval_number", value), true)}
        </div>
        {document.date_candidates && document.date_candidates.length > 0 && <div className="form-field">
          <p className="form-field__label">사진에서 읽은 날짜 후보</p>
          {document.date_candidates.map((candidate, index) => <p className="muted" key={index}>{candidate.raw} → {candidate.value}</p>)}
          <small className="muted">라벨과 날짜의 의미를 확인한 뒤 위 날짜 칸에 입력하세요.</small>
        </div>}
        {([ ["transaction_datetime", "거래일시"], ["card_number_masked", "마스킹 카드정보"],
          ["customer_business_number", "고객 사업자번호"] ] as const).map(([key, label]) => <div className="form-field" key={key}>
          <label className="form-field__label" htmlFor={key}>{label}</label>
          <input id={key} className="input" disabled={inputDisabled} value={document[key] ?? ""}
            onChange={e => editDocumentValue(key, e.target.value)} />
          {stateControl(key, label, document[key] ?? "", value => editDocumentValue(key, value), true)}
        </div>)}
        {receipt?.evidence_validation && <p className="muted">증빙 검사: {receipt.evidence_validation.validation_status}
          {receipt.evidence_validation.missing_fields.length ? ` · 누락: ${receipt.evidence_validation.missing_fields.join(", ")}` : ""}
          {receipt.evidence_validation.conflicts.length ? ` · 확인 필요: ${receipt.evidence_validation.conflicts.join(", ")}` : ""}
          <br />OCR 확정은 증빙 유효성이나 세금 공제 가능성을 확정하지 않습니다.</p>}
        {!separated ? (
          <>
            <p className="muted">기존 금액은 보존됩니다. 면세가 섞인 영수증은 과세·면세 금액을 구분해 입력하세요.</p>
            <div className="form-field">
              <label className="form-field__label">기존 공급가액</label>
              <input className="input" disabled={inputDisabled} value={supplyAmount} onChange={(e) => editValue("supply_amount", e.target.value, setSupplyAmount)} />
          {stateControl("supply_amount", "기존 공급가액", supplyAmount, setSupplyAmount)}
            </div>
            <div className="form-field">
              <label className="form-field__label">기존 총액</label>
              <input className="input" disabled={inputDisabled} value={amount} onChange={(e) => editValue("amount", e.target.value, setAmount)} />
          {stateControl("amount", "기존 총액", amount, setAmount)}
            </div>
            <button className="btn btn--secondary" disabled={inputDisabled} onClick={() => setSeparated(true)}>과세·면세 금액 구분 입력</button>
          </>
        ) : (
          <>
            <p className="muted">과세 공급가액 + 면세 금액 + 부가세 = 거래 총액입니다. 금액이 0임을 확인했으면 0을 입력하세요. 미기재·판독 실패·해당 없음은 빈칸과 상태로 기록합니다. 필수 금액이 비어 있거나 미확인이면 확정할 수 없습니다.</p>
            {([
              ["taxable_supply_amount", "과세 공급가액", taxable, setTaxable],
              ["tax_exempt_amount", "면세 금액", exempt, setExempt],
              ["transaction_amount", "거래 총액", transaction, setTransaction],
              ["payment_amount", "결제금액", payment, setPayment],
              ["subtotal_amount", "할인 전 합계", subtotal, setSubtotal],
            ] as const).map(([key, label, value, setter]) => (
              <div className="form-field" key={key}>
                <label className="form-field__label" htmlFor={key}>{label}{receipt?.money_sources?.[key]?.kind === "calculated" && value === numberText(receipt[key]) ? " · 계산" : ""}</label>
                <input id={key} className="input" inputMode="decimal" disabled={inputDisabled} value={value} onChange={(e) => editValue(key, e.target.value, setter)} />
                {stateControl(key, label, value, setter)}
              </div>
            ))}
          </>
        )}
        <div className="form-field">
          <label className="form-field__label">부가세{receipt?.money_sources?.vat_amount?.kind === "calculated" && vatAmount === numberText(receipt.vat_amount) ? " · 계산" : ""}</label>
          <input className="input" disabled={inputDisabled} value={vatAmount} onChange={(e) => editValue("vat_amount", e.target.value, setVatAmount)} />
          {stateControl("vat_amount", "부가세", vatAmount, setVatAmount)}
        </div>
        <div className="form-field">
          <label className="form-field__label">거래일</label>
          <input className="input" type="date" disabled={inputDisabled} value={issuedAt} onChange={(e) => editValue("date", e.target.value, setIssuedAt)} />
          {stateControl("date", "거래일", issuedAt, setIssuedAt)}
        </div>

        {error && (
          <div className="banner banner--error" style={{ marginTop: 16 }}>
            <span>⚠️</span>
            <div>{error}</div>
          </div>
        )}

        {receipt?.confirmed && (
          <div className="banner banner--info" style={{ marginTop: 16 }}>
            <span>✓</span>
            <div>이미 확정된 영수증입니다.
              {receipt.transaction_id && <button className="btn btn--secondary" onClick={() => navigate(`/transactions/${receipt.transaction_id}`)}>거래·증빙 연결 확인</button>}
            </div>
          </div>
        )}

        <div className="stack-gap-sm" style={{ marginTop: 24 }}>
          {<button className="btn btn--secondary" disabled={inputDisabled} onClick={() => void handleConfirm(false)}>저장하고 계산 값 확인</button>}
          <button
            className="btn btn--primary"
            disabled={inputDisabled}
            onClick={() => void handleConfirm()}
          >
            {saving ? "확정 중..." : "수정 확인 후 확정"}
          </button>
          {needsRefresh && (
            <button className="btn btn--secondary" disabled={saving} onClick={() => void handleReload()}>
              최신 상태 다시 불러오기
            </button>
          )}
          <button className="btn btn--secondary" onClick={() => navigate("/capture")}>
            다시 촬영하기
          </button>
        </div>
      </div>
    </div>
  );
}
