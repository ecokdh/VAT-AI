"""Conservative extraction of explicitly labelled receipt details; no inferred tax amounts."""
import re


def extract_details(text: str | None) -> dict:
    if not text:
        return {}
    details = {}
    patterns = {
        "business_number": r"(?:사업자\s*(?:등록)?\s*번호|사업자번호)\s*[:：]?\s*(\d{3}-?\d{2}-?\d{5})",
        "phone": r"(?:전화|TEL|연락처)\s*[:：]?\s*([\d() -]{8,20})",
        "address": r"(?:주소)\s*[:：]?\s*([^\n]{1,300})",
        "approval_number": r"(?:승인번호)\s*[:：]?\s*([A-Za-z0-9-]{1,40})",
        "receipt_number": r"(?:영수증번호|문서번호)\s*[:：]?\s*([A-Za-z0-9-]{1,60})",
        "payment_method": r"(?:결제수단|결제방법)\s*[:：]?\s*([^\n]{1,40})",
        "supply_amount": r"(?:공급가액|공급가)\s*[:：]?\s*([\d,]+)\s*원?",
        "vat_amount": r"(?:부가세|부가가치세)\s*[:：]?\s*([\d,]+)\s*원?",
        "tax_free_amount": r"(?:면세금액|면세액)\s*[:：]?\s*([\d,]+)\s*원?",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            details[key] = int(value.replace(",", "")) if key.endswith("amount") else value
    return details
