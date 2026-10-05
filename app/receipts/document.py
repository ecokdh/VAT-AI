"""Document facts and item evidence; no deduction decision is made here."""
from decimal import Decimal
import math
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, field_validator, model_validator


class Region(BaseModel):
    x: FiniteFloat
    y: FiniteFloat
    width: FiniteFloat = Field(ge=0)
    height: FiniteFloat = Field(ge=0)


class Evidence(BaseModel):
    kind: Literal["ocr", "manual", "calculated"]
    state: Literal["READ", "ABSENT", "FAILED", "UNREVIEWED", "NOT_APPLICABLE"] = "READ"
    boxes: list[Region] = Field(default_factory=list)
    confidence: FiniteFloat | None = Field(default=None, ge=0, le=1)
    rule: str | None = None


class StructuredItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str | None = None
    name: str = Field(min_length=1, max_length=500)
    original_name: str | None = None
    specification: str | None = None
    unit: str | None = None
    quantity: FiniteFloat | None = None
    printed_unit_price: FiniteFloat | None = Field(default=None, ge=0)
    effective_unit_price: FiniteFloat | None = None
    line_amount: FiniteFloat | None = None
    discount_amount: FiniteFloat | None = Field(default=None, ge=0)
    tax_type: Literal["UNKNOWN", "TAXABLE", "EXEMPT", "ZERO_RATED"] = "UNKNOWN"
    usage: Literal["UNKNOWN", "BUSINESS", "PERSONAL", "MIXED"] = "UNKNOWN"
    user_note: str | None = None
    sources: dict[str, Evidence] = Field(default_factory=dict)


class Discount(BaseModel):
    id: str
    kind: Literal["DISCOUNT", "COUPON"]
    scope: Literal["ITEM", "GROUP", "TRANSACTION"]
    amount: FiniteFloat = Field(ge=0)
    item_ids: list[str] = Field(default_factory=list)
    included_in_line_amounts: bool | None = None
    # A coupon may be included in the reported discount; do not subtract both.
    included_in_discount_id: str | None = None


class DocumentFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_type: Literal["CARD_RECEIPT", "CASH_RECEIPT", "GENERAL_RECEIPT", "TAX_INVOICE", "INVOICE", "UNKNOWN"] = "UNKNOWN"
    purchase_or_sales: Literal["PURCHASE", "SALE", "UNKNOWN"] = "UNKNOWN"
    supply_date: str | None = None
    document_issue_date: str | None = None
    payment_date: str | None = None
    transaction_datetime: str | None = None
    approval_number: str | None = None
    original_approval_number: str | None = None
    card_company: str | None = None
    card_number_masked: str | None = None
    card_last4: str | None = Field(default=None, pattern=r"^\d{4}$")
    customer_business_number: str | None = None
    merchant_business_number: str | None = None
    date_candidates: list[dict] = Field(default_factory=list)
    purchase_purpose: str | None = None
    adjustment_type: Literal["RETURN", "CANCELLATION", "CORRECTION"] | None = None
    discounts: list[Discount] = Field(default_factory=list)
    sources: dict[str, Evidence] = Field(default_factory=dict)
    review_reasons: list[str] = Field(default_factory=list)

    @field_validator("supply_date", "document_issue_date", "payment_date")
    @classmethod
    def valid_date(cls, value):
        if value is not None:
            from datetime import date
            if date.fromisoformat(value).isoformat() != value:
                raise ValueError("Use an ISO calendar date")
        return value

    @field_validator("transaction_datetime")
    @classmethod
    def valid_transaction_datetime(cls, value):
        if value is not None:
            import re
            from datetime import datetime
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2})?", value):
                raise ValueError("거래일시는 날짜와 시간을 함께 입력하세요. 예: 2026-10-05T10:30:00")
            value = datetime.fromisoformat(value).isoformat()
        return value

    @field_validator("card_number_masked")
    @classmethod
    def masked_card_only(cls, value):
        if value is not None:
            import re
            if not re.search(r"[*Xx•●]", value) or not re.fullmatch(r"[\d*Xx•● -]+", value):
                raise ValueError("Only masked card information may be stored")
        return value

    @model_validator(mode="after")
    def discount_links(self):
        discounts = {discount.id: discount for discount in self.discounts}
        if len(discounts) != len(self.discounts):
            raise ValueError("Discount IDs must be unique")
        for discount in self.discounts:
            if len(discount.item_ids) != len(set(discount.item_ids)):
                raise ValueError("Discount item references must be unique")
            if ((discount.scope == "ITEM" and len(discount.item_ids) != 1)
                    or (discount.scope == "GROUP" and not discount.item_ids)
                    or (discount.scope == "TRANSACTION" and discount.item_ids)):
                raise ValueError("Discount scope and item references disagree")
            seen = {discount.id}
            parent = discount.included_in_discount_id
            while parent is not None:
                if parent in seen or parent not in discounts:
                    raise ValueError("Discount inclusion must refer to an existing non-cyclic discount")
                seen.add(parent)
                parent = discounts[parent].included_in_discount_id
        return self


def complete_item(item: StructuredItem) -> StructuredItem:
    """An effective price is not the printed price; missing quantity stays missing."""
    data = item.model_dump(mode="json")
    data["effective_unit_price"] = None
    data["sources"].pop("effective_unit_price", None)
    if item.quantity not in (None, 0) and item.line_amount is not None:
        value = Decimal(str(item.line_amount)) / Decimal(str(item.quantity))
        parsed = float(value)
        representable = math.isfinite(parsed) and (value == 0 or parsed != 0)
        data["effective_unit_price"] = parsed if representable else None
        regions = {}
        for field in ("quantity", "line_amount"):
            source = item.sources.get(field)
            for box in source.boxes if source else []:
                regions[(box.x, box.y, box.width, box.height)] = box.model_dump()
        data["sources"]["effective_unit_price"] = {"kind": "calculated", "state": "READ" if representable else "FAILED",
            "rule": "line_amount_divided_by_quantity", "boxes": list(regions.values()), "confidence": None}
    return StructuredItem.model_validate(data)


def evidence_validation(receipt, document: DocumentFacts) -> dict:
    import json
    from app.receipts.money import MONEY_FIELDS, money_problem
    missing, conflicts, unreviewed = [], [], []
    money_sources = json.loads(getattr(receipt, "money_sources_json", None) or "{}")

    def require_reviewed(field, value, source):
        state = source.state if isinstance(source, Evidence) else (source or {}).get("state")
        if value is None or value == "" or state in ("ABSENT", "FAILED", "NOT_APPLICABLE", "UNREVIEWED"):
            if field not in missing:
                missing.append(field)
        if state == "UNREVIEWED":
            unreviewed.append(field)

    for field in ("vendor", "date", "business_number"):
        require_reviewed(field, getattr(receipt, field, None), document.sources.get(field))
    if receipt.business_number and (len(receipt.business_number) != 10 or not receipt.business_number.isdigit()):
        conflicts.append("business_number_format")
    for field in ("merchant_business_number", "customer_business_number"):
        value = getattr(document, field)
        if value and (len(value) != 10 or not value.isascii() or not value.isdigit()):
            conflicts.append(f"{field}_format")
    if document.merchant_business_number and receipt.business_number and document.merchant_business_number != receipt.business_number:
        conflicts.append("merchant_business_number_mismatch")
    if document.document_type == "UNKNOWN":
        missing.append("document_type")
    else:
        require_reviewed("document_type", document.document_type, document.sources.get("document_type"))
    if document.document_type in ("CARD_RECEIPT", "CASH_RECEIPT"):
        require_reviewed("approval_number", document.approval_number, document.sources.get("approval_number"))
    if document.document_type in ("TAX_INVOICE", "INVOICE"):
        for field in ("document_issue_date", "customer_business_number"):
            require_reviewed(field, getattr(document, field), document.sources.get(field))
    for field in ("taxable_supply_amount", "tax_exempt_amount", "vat_amount", "transaction_amount"):
        require_reviewed(field, getattr(receipt, field, None), money_sources.get(field))
    problem = money_problem({f: getattr(receipt, f) for f in MONEY_FIELDS}, required=True)
    if problem:
        if any(getattr(receipt, f) is None for f in ("taxable_supply_amount", "tax_exempt_amount", "vat_amount", "transaction_amount")):
            missing.append("amount_breakdown")
        else:
            conflicts.append(problem)
    conflicts.extend(document.review_reasons)
    invalid = any(getattr(receipt, f, None) is not None and getattr(receipt, f) < 0 for f in MONEY_FIELDS) and not document.adjustment_type
    return {"validation_status": "INVALID" if invalid else "CONFLICT" if conflicts else "INCOMPLETE" if missing else "VALID",
            "missing_fields": missing, "unreviewed_fields": unreviewed, "conflicts": conflicts,
            "external_business_verification": "NOT_PERFORMED", "deduction_status": "UNDETERMINED"}
