"""Conservative document metadata extraction from labelled OCR rows."""
import re
from datetime import datetime


def extract_metadata(boxes) -> dict:
    from app.receipts.kie import parse_date, parse_business_number, parse_amount, _financial_label
    result = {"sources": {}, "review_reasons": [], "date_candidates": []}
    rows = []
    for box in sorted(boxes, key=lambda b: (b.cy, b.x)):
        row = next((r for r in rows if abs(r[0].cy - box.cy) <= max(r[0].height, box.height) * .55), None)
        if row is None:
            rows.append([box])
        else:
            row.append(box)

    def evidence(row, state="READ"):
        confidence = [b.confidence for b in row if b.confidence is not None]
        return {"kind": "ocr", "state": state,
                "boxes": [{"x": b.x, "y": b.y, "width": b.width, "height": b.height} for b in row],
                "confidence": min(confidence) if confidence else None}

    def assign(key, value, row):
        if f"conflicting_{key}_candidates" in result["review_reasons"]:
            return
        if value is None:
            result["sources"].setdefault(key, evidence(row, "FAILED"))
        elif key in result and result[key] != value:
            result[key] = None
            result["sources"][key] = evidence(row, "UNREVIEWED")
            reason = f"conflicting_{key}_candidates"
            if reason not in result["review_reasons"]:
                result["review_reasons"].append(reason)
        else:
            result[key] = value
            result["sources"][key] = evidence(row)

    full_text = "\n".join(" ".join(b.text for b in sorted(row, key=lambda b: b.x)) for row in rows)
    types = []
    if "현금영수증" in full_text:
        types.append("CASH_RECEIPT")
    if re.search(r"신용카드\s*(매출|전표)|카드\s*매출전표", full_text):
        types.append("CARD_RECEIPT")
    # Invoice-specific extraction is intentionally unsupported.
    if "세금계산서" in full_text:
        types.append("TAX_INVOICE")
    elif "계산서" in full_text:
        types.append("INVOICE")
    if not types and any(re.fullmatch(r"[<>\[\]()【】*]*영수증[<>\[\]()【】*]*", re.sub(r"\s", "", "".join(b.text for b in row))) for row in rows):
        types.append("GENERAL_RECEIPT")
    if len(set(types)) == 1:
        result["document_type"] = types[0]
        matching = [b for row in rows for b in row if any(word in b.text for word in ("영수증", "전표", "계산서"))]
        result["sources"]["document_type"] = evidence(matching)
    elif types:
        result["review_reasons"].append("conflicting_document_type_candidates")

    adjustment_headings = []
    negative_totals = []
    for row in rows:
        compact = re.sub(r"\s", "", "".join(b.text for b in sorted(row, key=lambda b: b.x)))
        if re.fullmatch(r"[\[(*<【]?(반품|환불|교환|취소)(?:/반품|/교환|/환불)?(?:영수증|전표|매출전표)[\])*>】]?", compact):
            adjustment_headings.append(("CANCELLATION" if compact.lstrip("[(*<【").startswith("취소") else "RETURN", row))
        if _financial_label(compact, ("판매합계", "거래총액", "총금액", "총액", "결제금액", "받을금액", "합계")):
            # An item discount or a refund-policy notice cannot authorize signed totals.
            value_boxes = [b for b in row if parse_amount(b.text, allow_signed=True) is not None]
            if any(parse_amount(b.text, allow_signed=True) < 0 for b in value_boxes):
                negative_totals.append(row)
    if adjustment_headings and negative_totals:
        kinds = {kind for kind, _ in adjustment_headings}
        if len(kinds) == 1:
            assign("adjustment_type", kinds.pop(), [b for _, row in adjustment_headings for b in row] + [b for row in negative_totals for b in row])
        else:
            result["review_reasons"].append("conflicting_adjustment_type_candidates")

    for row in rows:
        text = " ".join(b.text for b in sorted(row, key=lambda b: b.x))
        compact = re.sub(r"\s", "", text)
        date = parse_date(text)
        if date:
            result["date_candidates"].append({"raw": text, "value": date.isoformat(), "source": evidence(row)})
        date_labels = {"supply_date": ("공급일",), "document_issue_date": ("발행일", "작성일자"),
                       "payment_date": ("결제일", "승인일")}
        for key, labels in date_labels.items():
            if any(label in compact for label in labels):
                assign(key, date.isoformat() if date else None, row)
        if any(label in compact for label in ("거래일시", "승인일시", "결제일시")):
            time = re.search(r"(?<!\d)([0-2]\d):([0-5]\d)(?::([0-5]\d))?(?!\d)", text)
            value = None
            if date and time:
                try:
                    value = datetime.combine(date, datetime.strptime(time.group(0), "%H:%M:%S" if time.group(3) else "%H:%M").time()).isoformat()
                except ValueError:
                    pass
            assign("transaction_datetime", value, row)
        match = re.search(r"(원\s*승인번호|승인번호)\s*[:：]?\s*([A-Za-z0-9-]+)", text)
        if match:
            assign("original_approval_number" if match.group(1).replace(" ", "").startswith("원") else "approval_number", match.group(2), row)
        elif "승인번호" in compact:
            assign("approval_number", None, row)
        if any(label in compact for label in ("사업자번호", "사업자등록번호")):
            key = "customer_business_number" if any(word in compact for word in ("공급받는자", "고객", "구매자")) else "merchant_business_number"
            assign(key, parse_business_number(text), row)
        if "카드번호" in compact:
            match = re.search(r"[\d*Xx•●]{4}(?:[- ]?[\d*Xx•●]{4}){1,3}", text)
            number = match.group(0).replace(" ", "") if match else None
            if number:
                digits = re.sub(r"\D", "", number)
                if not re.search(r"[*Xx•●]", number):
                    # Never persist a full unmasked PAN in normalized document facts.
                    number = "****-****-****-" + digits[-4:]
                assign("card_number_masked", number, row)
                trailing = re.search(r"(\d{4})$", number)
                if trailing:
                    assign("card_last4", trailing.group(1), row)
            else:
                assign("card_number_masked", None, row)
    return result
