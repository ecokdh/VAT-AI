"""클로바 글자 상자 좌표와 규칙으로 칸을 채운다. 학습 모델은 쓰지 않는다."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date as date_
from decimal import Decimal, InvalidOperation
import math
import re
from typing import Any


LABEL_TOTAL = ("총금액", "총액", "결제금액", "합계")
LABEL_SUPPLY = ("공급가액", "공급가")
LABEL_VAT = ("부가세", "부가가치세")
EXPLICIT_TRANSACTION_LABELS = ("transaction_amount", "거래총액", "할인후합계", "최종거래금액")
FINANCIAL_LABELS = {
    "taxable_supply_amount": ("과세공급가액", "과세물품가액", "과세물품", "공급가액"),
    "tax_exempt_amount": ("면세물품가액", "면세물품", "면세금액", "면세합계", "면세합"),
    "transaction_amount": ("거래총액", "할인후합계", "최종거래금액", "총금액", "총액", "합계금액", "합계"),
    "payment_amount": ("총결제금액", "결제금액", "받을금액", "신용카드승인", "카드/전자상품권", "신용카드지불", "현금지불"),
    "subtotal_amount": ("할인전합계", "주문합계", "주문금액", "상품합계", "소계"),
}


@dataclass(frozen=True)
class TextBox:
    text: str
    x: float
    y: float
    width: float
    height: float
    confidence: float | None = None
    line_break: bool | None = None

    @property
    def cx(self) -> float:
        return self.x + self.width / 2

    @property
    def cy(self) -> float:
        return self.y + self.height / 2


def boxes_from_fields(fields: list[dict[str, Any]]) -> tuple[TextBox, ...]:
    boxes: list[TextBox] = []
    for field in fields:
        text = field.get("inferText")
        if not isinstance(text, str) or not text.strip():
            continue
        box = _box_from_poly(field.get("boundingPoly"), text.strip())
        if box is not None:
            confidence = field.get("inferConfidence")
            confidence = float(confidence) if isinstance(confidence, (float, int)) and not isinstance(confidence, bool) and math.isfinite(confidence) and 0 <= confidence <= 1 else None
            box = replace(box, confidence=confidence, line_break=field.get("lineBreak") if isinstance(field.get("lineBreak"), bool) else None)
            boxes.append(box)
    return tuple(boxes)


def boxes_as_dicts(boxes: tuple[TextBox, ...]) -> list[dict[str, float | str]]:
    return [
        {
            "text": box.text,
            "x": box.x,
            "y": box.y,
            "width": box.width,
            "height": box.height,
            "confidence": box.confidence,
            "line_break": box.line_break,
        }
        for box in boxes
    ]


def fill_from_boxes(current: dict[str, Any], boxes: tuple[TextBox, ...]) -> dict[str, Any]:
    filled = dict(current)
    from app.receipts.metadata import extract_metadata
    metadata = extract_metadata(boxes)
    filled["document"] = metadata
    allow_signed = bool(metadata.get("adjustment_type"))
    if "merchant_business_number" in metadata:
        filled["business_number"] = metadata["merchant_business_number"]
    elif metadata.get("customer_business_number"):
        filled["business_number"] = None
    if not filled.get("business_number") and not metadata.get("customer_business_number") and "merchant_business_number" not in metadata:
        for box in boxes:
            parsed = parse_business_number(box.text)
            if parsed:
                filled["business_number"] = parsed
                break
    if filled.get("date") is None:
        for box in boxes:
            parsed = parse_date(box.text)
            if parsed:
                filled["date"] = parsed
                break
    if filled.get("amount") is None:
        filled["amount"] = _amount_near_label(boxes, LABEL_TOTAL, allow_signed=allow_signed)
    if filled.get("supply_amount") is None:
        filled["supply_amount"] = _amount_near_label(boxes, LABEL_SUPPLY, allow_signed=allow_signed)
    if filled.get("vat_amount") is None:
        filled["vat_amount"] = _amount_near_label(boxes, LABEL_VAT, allow_signed=allow_signed)
    if not filled.get("vendor"):
        filled["vendor"] = _top_vendor(boxes)
    for field in ("vendor", "date", "business_number"):
        value = filled.get(field)
        matching = [box for box in boxes if value is not None and (
            box.text == value if field == "vendor" else parse_date(box.text) == value if field == "date"
            else parse_business_number(box.text) == value)]
        metadata["sources"][field] = {"kind": "ocr", "state": "READ" if value is not None else "UNREVIEWED",
            "boxes": [{"x": box.x, "y": box.y, "width": box.width, "height": box.height} for box in matching],
            "confidence": min((box.confidence for box in matching if box.confidence is not None), default=None)}
    reasons = list(filled.get("review_reasons", []))
    for field, labels in {**FINANCIAL_LABELS, "vat_amount": LABEL_VAT}.items():
        if field == "transaction_amount" and _order_with_explicit_total([box.text for box in boxes]):
            labels = EXPLICIT_TRANSACTION_LABELS
        if boxes:
            # '면세합계'를 '합계'로 읽거나, 다른 금액의 라벨을 숫자로 쓰지 않는다.
            candidates = tuple(
                replace(box, text=re.sub(r"\s", "", box.text))
                for box in boxes
                if _financial_label(box.text, labels) or not any(
                    label in re.sub(r"\s", "", box.text)
                    for names in FINANCIAL_LABELS.values() for label in names
                )
            )
            label_boxes = tuple(box for box in candidates if _financial_label(box.text, labels) and not (field == "transaction_amount" and any(
                re.sub(r"\s", "", other.text) in ("과세", "면세", "과세합계", "면세합계")
                and abs(other.cy - box.cy) <= max(other.height, box.height) * .55 for other in boxes)))
            if label_boxes:
                values = {_amount_near_label(tuple(b for b in candidates if not _financial_label(b.text, labels) or b == label), labels, allow_signed=allow_signed) for label in label_boxes}
                values.discard(None)
                split_payment = field == "payment_amount" and all(any(
                    _financial_label(label.text, (channel,)) and
                    _amount_near_label(tuple(b for b in candidates if not _financial_label(b.text, labels) or b == label),
                        (channel,), allow_signed=allow_signed) not in (None, 0)
                    for label in label_boxes) for channel in ("신용카드지불", "현금지불"))
                if len(values) == 1 and not split_payment:
                    filled[field] = values.pop()
                elif len(values) > 1 or split_payment:
                    filled[field] = None
                    reasons.append(f"conflicting_{field}_candidates")
    filled = _separate_order_subtotal(filled, [box.text for box in boxes])
    if filled.get("transaction_amount") is not None:
        filled["amount"] = filled["transaction_amount"]
    elif "conflicting_transaction_amount_candidates" in reasons:
        filled["amount"] = None
    filled["review_reasons"] = reasons
    filled["money_evidence"] = {field: _money_evidence(boxes, labels, filled.get(field),
        f"conflicting_{field}_candidates" in reasons, allow_signed=allow_signed) for field, labels in {**FINANCIAL_LABELS, "vat_amount": LABEL_VAT,
            "amount": FINANCIAL_LABELS["transaction_amount"], "supply_amount": LABEL_SUPPLY}.items()}
    structured = extract_line_items(boxes)
    if structured:
        filled["line_items"] = structured
        filled["items"] = [item["name"] for item in structured]
    filled["text_boxes"] = boxes_as_dicts(boxes)
    return filled


def _money_evidence(boxes, labels, value, conflict=False, *, allow_signed=False):
    labels_found = [box for box in boxes if _financial_label(box.text, labels)]
    regions = list(labels_found) if conflict else []
    if not conflict and value is not None:
        for label in labels_found:
            if parse_amount(label.text, allow_signed=allow_signed) == value:
                regions = [label]
                break
            candidates = []
            for box in boxes:
                if parse_amount(box.text, allow_signed=allow_signed) != value or _is_phone_or_id(box.text) or parse_date(box.text) or parse_business_number(box.text):
                    continue
                right = box.cx >= label.cx - 8 and abs(box.cy - label.cy) <= max(24, label.height)
                below = box.cy >= label.cy and box.cy - label.cy <= max(48, label.height * 3) and abs(box.cx - label.cx) <= max(80, label.width * 2)
                if right or below:
                    candidates.append(((0 if right else 100000) + abs(box.cy - label.cy) * 100 + abs(box.cx - label.cx), box))
            if candidates:
                regions = [label, min(candidates, key=lambda pair: pair[0])[1]]
                break
    confidence = [box.confidence for box in regions if box.confidence is not None]
    return {"state": "UNREVIEWED" if conflict or not labels_found and value is None else "FAILED" if value is None else "READ",
            "boxes": [{"x": box.x, "y": box.y, "width": box.width, "height": box.height} for box in regions],
            "confidence": min(confidence) if confidence else None}


def extract_line_items(boxes: tuple[TextBox, ...]) -> list[dict]:
    """Connect printed columns and preserve partial rows without invented defaults."""
    if not boxes:
        return []
    rows: list[list[TextBox]] = []
    for box in sorted(boxes, key=lambda b: (b.cy, b.x)):
        nearby = next((row for row in reversed(rows[-3:]) if abs(sum(b.cy for b in row) / len(row) - box.cy) <= max(box.height * .65, 8)), None)
        if nearby is None:
            rows.append([box])
        else:
            nearby.append(box)
    for row in rows:
        row.sort(key=lambda b: b.x)
    left = min(b.x for b in boxes)
    width = max(b.x + b.width for b in boxes) - left
    numeric = re.compile(r"^-?\d[\d,]*(?:\.\d+)?[*#]?원?$")
    code = re.compile(r"^[$*#]*\[?\d{3,}\]?$|^[*#:]$")
    footer = ("합계", "부가세", "과세물품", "면세물품", "공급가", "결제", "에누리", "할인금액", "승인", "받을금액", "총수량",
              "총구매액", "상품수", "면세합", "과세합", "주문금액", "계좌이체")
    headers = {"quantity": ("수량", "개수"), "printed_unit_price": ("단가", "판매단가"), "line_amount": ("금액", "행금액", "판매금액")}
    header_start = next((index for index, row in enumerate(rows) if sum(
        any(b.text.strip(" :：") in labels for b in row) for labels in headers.values()) >= 2), None)
    anchors = {}
    result, pending, last_names = [], [], []
    started = False

    def evidence(parts):
        confidences = [b.confidence for b in parts if b.confidence is not None]
        return {"kind": "ocr", "state": "READ", "boxes": [{"x": b.x, "y": b.y, "width": b.width, "height": b.height} for b in parts],
                "confidence": min(confidences) if confidences else None}

    def read(box):
        if box is None or isinstance(box, list):
            return None
        try:
            value = float(box.text.replace(",", "").rstrip("*#원"))
            return value if math.isfinite(value) else None
        except ValueError:
            return None

    def name_values(names):
        original_name = " ".join(b.text for b in names).strip()
        name = re.sub(r"^\d{2,3}(?:\s+|[*#])", "", original_name).strip()
        return name, original_name

    def append_item(names, assigned):
        nonlocal last_names
        name, original_name = name_values(names)
        if not name or not re.search(r"[가-힣A-Za-z]", name):
            return
        sources = {"name": evidence(names)}
        values = {}
        for field in headers:
            box = assigned.get(field)
            value = read(box)
            if (field == "quantity" and value is not None and abs(value) > 999) or (field == "printed_unit_price" and value is not None and value < 0):
                value = None
            values[field] = value
            sources[field] = evidence(box if isinstance(box, list) else [box]) if box else {"kind": "ocr", "state": "UNREVIEWED"}
            if box and value is None:
                sources[field]["state"] = "FAILED"
        result.append({"name": name, "original_name": original_name, **values, "sources": sources})
        last_names = list(names)

    def extend_open_name(names):
        nonlocal last_names
        if not result or not last_names or pending:
            return False
        previous = result[-1]["original_name"]
        # Adjacency alone cannot distinguish a new partial item from a wrapped name.
        if not any(previous.count(opening) > previous.count(closing) for opening, closing in (("(", ")"), ("[", "]"))):
            return False
        gap = min(b.y for b in names) - max(b.y + b.height for b in last_names)
        aligned = abs(min(b.x for b in names) - min(b.x for b in last_names)) <= max(width * .08, 20)
        if gap > max(b.height for b in names) * 1.5 or not aligned:
            return False
        last_names = [*last_names, *names]
        name, original = name_values(last_names)
        result[-1].update(name=name, original_name=original)
        result[-1]["sources"]["name"] = evidence(last_names)
        return True

    for index, row in enumerate(rows):
        if header_start is not None and index < header_start:
            continue
        compact = re.sub(r"\s", "", " ".join(b.text for b in row))
        found = {key: box for box in row for key, labels in headers.items() if box.text.strip(" :：") in labels}
        if len(found) >= 2:
            if pending and started:
                append_item(pending, {})
            anchors, pending = {key: box.cx for key, box in found.items()}, []
            continue
        if any(word in compact for word in footer):
            if pending and (started or anchors):
                append_item(pending, {})
            pending = []
            if started:
                break
            continue
        numbers = [b for b in row if numeric.fullmatch(b.text.replace(" ", "")) and b.cx > left + width * .45]
        column_boxes = [b for b in row if anchors and (b in numbers or re.fullmatch(r"[-\d,.OoIl?]+원?", b.text.replace(" ", "")))
                        and b.cx >= min(anchors.values()) - max(width * .14, 20)]
        name_boxes = [b for b in row if b not in numbers and not code.fullmatch(b.text.replace(" ", ""))
                      and b not in column_boxes
                      and b.cx < left + width * .72 and not parse_date(b.text)]
        has_index = any(re.fullmatch(r"\d{1,3}", b.text) and b.cx < left + width * .15 for b in row)
        meta = any(word in compact for word in ("상품명", "품명", "제품명", "사업자", "주소", "전화", "판매일", "발행일", "거래일", "거래번호", "주유기번호", "POS", "계산원"))
        if meta:
            pending = []
            last_names = []
            continue
        if not numbers and not column_boxes:
            if name_boxes:
                if not has_index and extend_open_name(name_boxes):
                    continue
                close = pending and min(b.y for b in name_boxes) - max(b.y + b.height for b in pending) <= max(b.height for b in name_boxes) * 1.5
                if has_index or pending and not close:
                    if pending and (started or anchors):
                        append_item(pending, {})
                    pending = name_boxes
                else:
                    pending.extend(name_boxes)
            else:
                # A barcode or separator ends an already emitted item's name region.
                last_names = []
            continue
        # A barcode-only row does not replace a pending product name.
        if pending and not has_index:
            close = min(b.y for b in row) - max(b.y + b.height for b in pending) <= max(b.height for b in row) * 1.5
            if close:
                name_boxes = [*pending, *name_boxes]
            elif started or anchors:
                append_item(pending, {})
        pending = []
        if not name_boxes:
            continue
        assigned = {}
        numbers.sort(key=lambda b: b.cx)
        if not anchors and not started and len(numbers) < 2:
            pending = name_boxes
            continue
        if anchors:
            tolerance = max(width * .14, 20)
            for box in column_boxes:
                field = min(anchors, key=lambda key: abs(box.cx - anchors[key]))
                if abs(box.cx - anchors[field]) <= tolerance:
                    # Conflicting boxes in one column are left unresolved.
                    previous = assigned.get(field)
                    assigned[field] = box if previous is None else [*(previous if isinstance(previous, list) else [previous]), box]
        elif len(numbers) >= 3:
            assigned = dict(zip(("printed_unit_price", "quantity", "line_amount"), numbers[-3:]))
        elif numbers[-1].cx >= left + width * .72:
            assigned["line_amount"] = numbers[-1]
        else:
            pending = name_boxes
            continue
        append_item(name_boxes, assigned)
        started = True
    if pending and (started or anchors):
        append_item(pending, {})
    return result


def _financial_label(text: str, labels: tuple[str, ...]) -> bool:
    compact = re.sub(r"\s", "", text)
    compact = re.sub(r"^\([*#]\)", "", compact)
    return any(re.fullmatch(re.escape(label) + r"[:：]?[-\d,.원]*", compact) for label in labels)


def financial_from_fields(fields: list[dict]) -> dict:
    """좌표 없는 템플릿/텍스트도 명시적 라벨만 사용한다."""
    result = {}
    texts = [field.get("inferText", "").strip() for field in fields if isinstance(field.get("inferText"), str)]
    order_explicit = _order_with_explicit_total(texts + [str(field.get("name", "")) for field in fields])
    for key, labels in FINANCIAL_LABELS.items():
        if key == "transaction_amount" and order_explicit:
            labels = EXPLICIT_TRANSACTION_LABELS
        values = _financial_values(fields, texts, (key, *labels))
        split_payment = key == "payment_amount" and all(
            _read_financial_amount(fields, texts, (channel,)) not in (None, 0)
            for channel in ("신용카드지불", "현금지불"))
        result[key] = next(iter(values)) if len(values) == 1 and not split_payment else None
        if len(values) > 1 or split_payment:
            result.setdefault("review_reasons", []).append(f"conflicting_{key}_candidates")
    result["_transaction_explicit"] = any(field.get("name") in ("transaction_amount", "거래총액", "할인후합계", "최종거래금액") for field in fields)
    if any("주문서" in re.sub(r"\s", "", text) or "주문내역" in re.sub(r"\s", "", text) for text in texts) and result.get("subtotal_amount") is None:
        result["subtotal_amount"] = _read_financial_amount(fields, texts, ("총금액", "총액", "합계금액", "합계"))
    return _separate_order_subtotal(result, texts + [str(field.get("name", "")) for field in fields])


def _order_with_explicit_total(texts: list[str]) -> bool:
    return any("주문서" in re.sub(r"\s", "", text) or "주문내역" in re.sub(r"\s", "", text) for text in texts) and any(
        _financial_label(text, EXPLICIT_TRANSACTION_LABELS) for text in texts)


def _read_financial_amount(fields: list[dict], texts: list[str], labels: tuple[str, ...]) -> float | None:
    values = _financial_values(fields, texts, labels)
    return next(iter(values)) if len(values) == 1 else None


def _financial_values(fields: list[dict], texts: list[str], labels: tuple[str, ...]) -> set[float]:
    values = set()
    for label in labels:
        for field in fields:
            if field.get("name") == label:
                value = parse_amount(field.get("inferText"))
                if value is not None:
                    values.add(value)
        for index, text in enumerate(texts):
            if _financial_label(text, (label,)):
                value = parse_amount(text)
                if value is None and not any(f.get("boundingPoly") for f in fields) and index + 1 < len(texts) and re.fullmatch(r"[-\d,.]+원?", texts[index + 1]):
                    value = parse_amount(texts[index + 1])
                if value is not None:
                    values.add(value)
    return values


def _separate_order_subtotal(values: dict, texts: list[str]) -> dict:
    compact = [re.sub(r"\s", "", text) for text in texts]
    if any("주문서" in text or "주문내역" in text for text in compact) and not values.get("_transaction_explicit") and not any(
        text == "transaction_amount" or _financial_label(text, ("거래총액", "할인후합계", "최종거래금액"))
        for text in compact
    ):
        if values.get("subtotal_amount") is None:
            values["subtotal_amount"] = values.get("transaction_amount")
        values["transaction_amount"] = None
    return values


def _is_phone_or_id(text: str) -> bool:
    digits = re.sub(r"\D", "", text)
    if text.strip().startswith(("010", "011", "016", "017", "018", "019", "02", "070")):
        return True
    if text.count("-") >= 2 and len(digits) >= 9:
        return True
    return False


def parse_amount(value: str | None, *, allow_signed: bool = False) -> float | None:
    if not value:
        return None
    match = re.search(r"-?\d[\d,]*(?:\.\d+)?", value.replace(" ", ""))
    if match is None:
        return None
    try:
        amount = Decimal(match.group(0).replace(",", ""))
    except InvalidOperation:
        return None
    if not amount.is_finite() or amount < 0 and not allow_signed:
        return None
    parsed = float(amount)
    return parsed if math.isfinite(parsed) else None


def parse_business_number(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    if len(digits) != 10:
        return None
    return digits


def parse_date(value: str | None) -> date_ | None:
    if not value:
        return None
    match = re.search(r"(20\d{2})\D+(\d{1,2})\D+(\d{1,2})", value)
    if match is None:
        return None
    try:
        return date_(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def _box_from_poly(poly: object, text: str) -> TextBox | None:
    if not isinstance(poly, dict):
        return None
    vertices = poly.get("vertices")
    if not isinstance(vertices, list) or not vertices:
        return None
    xs: list[float] = []
    ys: list[float] = []
    for vertex in vertices:
        if not isinstance(vertex, dict):
            continue
        try:
            xs.append(float(vertex.get("x")))
            ys.append(float(vertex.get("y")))
        except (TypeError, ValueError):
            continue
    if not xs or not ys:
        return None
    left, top = min(xs), min(ys)
    return TextBox(text=text, x=left, y=top, width=max(xs) - left, height=max(ys) - top)


def _amount_near_label(boxes: tuple[TextBox, ...], labels: tuple[str, ...], *, allow_signed: bool = False) -> float | None:
    label_boxes = [box for box in boxes if any(label in box.text for label in labels)]
    number_boxes = []
    for box in boxes:
        if any(label in box.text for label in LABEL_TOTAL + LABEL_SUPPLY + LABEL_VAT + tuple(label for labels_ in FINANCIAL_LABELS.values() for label in labels_)):
            continue
        if _is_phone_or_id(box.text) or parse_date(box.text) or parse_business_number(box.text):
            continue
        value = parse_amount(box.text, allow_signed=allow_signed)
        if value is not None:
            number_boxes.append((box, value))
    for label_box in label_boxes:
        inline = parse_amount(label_box.text, allow_signed=allow_signed)
        if inline is not None:
            return inline
        nearest: tuple[float, float] | None = None
        for box, value in number_boxes:
            right = box.cx >= label_box.cx - 8 and abs(box.cy - label_box.cy) <= max(24, label_box.height)
            below = (
                box.cy >= label_box.cy
                and box.cy - label_box.cy <= max(48, label_box.height * 3)
                and abs(box.cx - label_box.cx) <= max(80, label_box.width * 2)
            )
            if not (right or below):
                continue
            # Same-row values outrank values in the following financial row.
            distance = (0 if right else 100000) + abs(box.cy - label_box.cy) * 100 + abs(box.cx - label_box.cx)
            if nearest is None or distance < nearest[0]:
                nearest = (distance, value)
        if nearest is not None:
            return nearest[1]
    return None


def _top_vendor(boxes: tuple[TextBox, ...]) -> str | None:
    skip = ("영수증", "거래", "합계", "총액", "부가", "카드", "승인", "공급가", "사업자")
    ordered = sorted(boxes, key=lambda box: (box.y, box.x))
    for box in ordered:
        if parse_amount(box.text) is not None:
            continue
        if parse_date(box.text) is not None:
            continue
        if parse_business_number(box.text):
            continue
        if any(word in box.text for word in skip):
            continue
        if len(box.text) < 2:
            continue
        return box.text
    return None
