"""Deterministic sales evidence graph: collect -> normalize -> scope -> reconcile -> aggregate -> validate -> finalize.

This flow reuses reviewed sales-document extractions. It never parses Hometax spreadsheets,
uses POS settlement totals, or changes previously generated returns.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import update
from sqlmodel import Session, select

from app.auth.models import User
from app.business.models import BusinessProfile, TaxProfileV2
from app.common.exceptions import AppException
from app.sales_filing.models import SalesFilingWorkflow
from app.sales_monthly.models import MonthlySalesDocument
from app.sales_monthly.spreadsheet import PG_PAYMENTS, VERSION as SPREADSHEET_VERSION, restore_document
from app.vat_return.engine import STANDARD_RATE, period_bounds

SOURCE_STATUSES = {"확인 완료", "해당 없음 확인", "자료 없음", "검토 필요"}
SOURCES = ("hometax_card", "hometax_cash_receipt", "hometax_sales_invoice", "pg", "unissued_sales")
SOURCE_LABELS = {
    "hometax_card": "홈택스 카드",
    "hometax_cash_receipt": "홈택스 현금영수증",
    "hometax_sales_invoice": "홈택스 매출 세금계산서",
    "pg": "PG·플랫폼",
    "unissued_sales": "미발급 현금·계좌이체 매출",
}
EXPECTED_DOC_TYPES = {
    "hometax_card": {"홈택스카드"},
    "hometax_cash_receipt": {"홈택스현금영수증"},
    "hometax_sales_invoice": {"매출세금계산서"},
    "pg": {"홈택스판매결제대행", "플랫폼정산"},
    "unissued_sales": {"기타매출장"},
}
HOMETAX_SOURCES = {"hometax_card", "hometax_cash_receipt", "hometax_sales_invoice"}
CARD_SOURCES = {"hometax_card", "hometax_cash_receipt"}
TAXABLE_VALUES = {"과세", "과세분", "standard", "taxable"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _default_checks() -> dict[str, dict[str, Any]]:
    return {
        source: {
            "status": "자료 없음",
            "query_start": None,
            "query_end": None,
            "basis": None,
            "document_ids": [],
            "reason": None,
        }
        for source in SOURCES
    }


def _case(session: Session, user_id: uuid.UUID, period: str) -> SalesFilingWorkflow:
    case = session.exec(select(SalesFilingWorkflow).where(
        SalesFilingWorkflow.user_id == user_id, SalesFilingWorkflow.period == period
    )).first()
    if case is None:
        case = SalesFilingWorkflow(user_id=user_id, period=period)
        session.add(case)
        session.flush()
    return case


def _period_dates(period: str) -> tuple[date, date]:
    try:
        return period_bounds(period, "general")
    except ValueError as exc:
        raise AppException(400, "UNSUPPORTED_TAX_PERIOD", "2026년 일반과세자 확정 신고기간만 지원합니다.") from exc


def _issue(code: str, key: Any, question: str, *, source: str | None = None,
           documents: list[int] | None = None, row: int | None = None,
           input_key: str | None = None, impact: int | None = None) -> dict[str, Any]:
    identity = {"code": code, "source": source, "documents": documents or [], "row": row, "input": input_key, "key": key}
    return {
        "issue_id": _fingerprint(identity)[:24],
        "reason_code": code,
        "source": source,
        "related_documents": documents or [],
        "related_row": row,
        "input_key": input_key,
        "impact_amount": impact,
        "question": question,
    }


def _resolution_map(case: SalesFilingWorkflow) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in _loads(case.feedback_json, []):
        current = result.setdefault(item["issue_id"], {})
        current.update({key: value for key, value in item.items() if value is not None})
    return result


def _profile(session: Session, user_id: uuid.UUID) -> BusinessProfile | None:
    return session.exec(select(BusinessProfile).where(BusinessProfile.user_id == user_id)).first()


def _tax_profile(session: Session, user_id: uuid.UUID) -> TaxProfileV2 | None:
    return session.exec(select(TaxProfileV2).where(TaxProfileV2.user_id == user_id)).first()


def _selected_documents(session: Session, checks: dict[str, dict[str, Any]], user_id: uuid.UUID) -> tuple[dict[int, MonthlySalesDocument], list[dict[str, Any]]]:
    ids = list(dict.fromkeys(
        int(document_id)
        for item in checks.values()
        for document_id in item.get("document_ids", [])
        if str(document_id).isdigit()
    ))
    if not ids:
        return {}, []
    docs = session.exec(select(MonthlySalesDocument).where(
        MonthlySalesDocument.user_id == user_id,
        MonthlySalesDocument.id.in_(ids),
    )).all()
    found = {doc.id: doc for doc in docs}
    missing = [document_id for document_id in ids if document_id not in found]
    return found, [{"document_id": item} for item in missing]


def _source_range_issue(source: str, check: dict[str, Any], start: date, end: date) -> str | None:
    try:
        query_start = date.fromisoformat(check.get("query_start") or "")
        query_end = date.fromisoformat(check.get("query_end") or "")
    except ValueError:
        return f"{SOURCE_LABELS[source]} 조회 시작일·종료일을 기록해 주세요."
    if query_start > start or query_end < end.fromordinal(end.toordinal() - 1):
        return f"{SOURCE_LABELS[source]} 자료가 신고기간 전체({start.isoformat()}~{(end.fromordinal(end.toordinal() - 1)).isoformat()})를 조회했는지 확인해 주세요."
    if not (check.get("basis") or "").strip():
        return f"{SOURCE_LABELS[source]} 조회 기준(승인월·작성일 등)을 기록해 주세요."
    return None


def _row_date(value: str | None) -> tuple[date | None, str | None]:
    value = (value or "").strip()
    if not value:
        return None, None
    if re.fullmatch(r"\d{4}-\d{2}", value):
        try:
            return date.fromisoformat(value + "-01"), "month"
        except ValueError:
            return None, "invalid"
    try:
        return date.fromisoformat(value[:10]), "day"
    except ValueError:
        return None, "invalid"


def _amounts(row: dict[str, Any], *, allow_negative: bool = False) -> tuple[int, int, int] | None:
    supply = row.get("공급가액")
    vat = row.get("부가세")
    total = row.get("합계금액")
    if total is None and (row.get("카드금액") is not None or row.get("기타결제금액") is not None):
        total = (row.get("카드금액") or 0) + (row.get("기타결제금액") or 0)
    if total is None and supply is not None and vat is not None:
        total = supply + vat
    if total is None:
        # The platform's net deposit is deliberately not a sales amount.
        if supply is None:
            return None
        vat = vat if vat is not None else supply * STANDARD_RATE // 100
        total = supply + vat
    if supply is None:
        supply = -((-int(total) * 100 + 55) // 110) if total < 0 else (int(total) * 100 + 55) // 110
    if vat is None:
        vat = int(total) - int(supply)
    amounts = (supply, vat, total)
    all_nonnegative = all(isinstance(amount, int) and amount >= 0 for amount in amounts)
    all_nonpositive = allow_negative and all(isinstance(amount, int) and amount <= 0 for amount in amounts)
    if not (all_nonnegative or all_nonpositive):
        return None
    if supply + vat != total:
        return None
    return supply, vat, total


def _evidence_reference(row: dict[str, Any]) -> str | None:
    for name in ("승인번호", "주문번호", "원승인번호"):
        value = (row.get(name) or "").strip()
        if value:
            return value
    return None


def _saved_document(doc: MonthlySalesDocument, raw: str) -> dict[str, Any]:
    document = _loads(raw, {})
    return restore_document(document) if doc.contract_version == SPREADSHEET_VERSION else document


def _normalize_document_rows(
    *, source: str, document_id: int, doc: MonthlySalesDocument,
    check: dict[str, Any], profile: BusinessProfile | None,
    start: date, end: date, period: str, resolutions: dict[str, dict[str, Any]], issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    try:
        document = _saved_document(doc, doc.review_json)
        evidence = document.get("매출증빙") or {}
    except AttributeError:
        document, evidence = {}, {}
    doc_type = evidence.get("문서유형")
    if doc.deleted_at is not None:
        issues.append(_issue("SOURCE_DOCUMENT_DELETED", document_id, f"선택한 문서 {document_id}가 휴지통에 있습니다. 복원하거나 다른 자료를 선택해 주세요.", source=source, documents=[document_id]))
        return []
    if doc.status != "reviewed":
        issues.append(_issue("DOCUMENT_NOT_REVIEWED", document_id, f"문서 {document_id} 검토본을 먼저 확인해 주세요.", source=source, documents=[document_id]))
        return []
    if doc_type == "POS정산":
        issues.append(_issue("POS_NOT_A_FILING_SOURCE", document_id, f"문서 {document_id}는 POS 월정산입니다. 신고 매출 근거로 선택하지 말고 홈택스 자료를 연결해 주세요.", source=source, documents=[document_id]))
        return []
    if doc_type == "매출계산서":
        issues.append(_issue("OUT_OF_SCOPE_EXEMPT_INVOICE", document_id, f"문서 {document_id}가 면세 매출계산서로 분류됐습니다. 과세·면세 혼재 여부를 검토해 주세요.", source=source, documents=[document_id]))
        return []
    if doc_type not in EXPECTED_DOC_TYPES[source]:
        issues.append(_issue("DOCUMENT_SOURCE_MISMATCH", document_id, f"문서 {document_id}의 유형({doc_type or '확인 불가'})이 {SOURCE_LABELS[source]} 자료와 맞는지 확인해 주세요.", source=source, documents=[document_id]))
        return []

    business = document.get("사업장") or {}
    document_number = _digits(business.get("사업자등록번호"))
    expected_number = _digits(profile.business_number if profile else None)
    if not document_number or not expected_number or document_number != expected_number:
        issues.append(_issue("BUSINESS_NUMBER_UNCONFIRMED", document_id, f"문서 {document_id}의 사업자번호가 느린오후카페 사업자번호와 일치하는지 확인해 주세요.", source=source, documents=[document_id]))

    invoice_list = doc_type == "매출세금계산서" and doc.contract_version.startswith("hometax-spreadsheet-")
    pg_sheet = doc_type == "홈택스판매결제대행" and doc.contract_version.startswith("hometax-spreadsheet-")
    doc_range_start = evidence.get("기간시작")
    doc_range_end = evidence.get("기간종료")
    document_basis = (evidence.get("기준일종류") or "").strip()
    declared_basis = (check.get("basis") or "").strip()
    if not document_basis or not declared_basis or (document_basis not in declared_basis and declared_basis not in document_basis):
        issues.append(_issue("SOURCE_BASIS_MISMATCH", document_id, f"문서 {document_id}의 기준일({document_basis or '확인 불가'})과 출처 조회 기준({declared_basis or '확인 불가'})이 같은지 확인해 주세요.", source=source, documents=[document_id]))
    try:
        parsed_doc_start = date.fromisoformat(doc_range_start or "")
        parsed_doc_end = date.fromisoformat(doc_range_end or "")
        parsed_lookup_start = date.fromisoformat(check.get("query_start") or "")
        parsed_lookup_end = date.fromisoformat(check.get("query_end") or "")
        if parsed_doc_start < parsed_lookup_start or parsed_doc_end > parsed_lookup_end:
            raise ValueError("document range falls outside the declared lookup scope")
        if parsed_doc_end < start or parsed_doc_start >= end:
            raise ValueError("document range does not overlap the filing period")
        if source == "hometax_cash_receipt" and document_basis == "거래년월" and (
            parsed_doc_start > start or parsed_doc_end.toordinal() + 1 < end.toordinal()
        ):
            raise ValueError("cash summary must cover the filing period")
        if (invoice_list or pg_sheet) and (parsed_doc_start != start or parsed_doc_end.toordinal() + 1 != end.toordinal()):
            raise ValueError("the export must match the filing period")
    except ValueError:
        issues.append(_issue("DOCUMENT_PERIOD_UNCONFIRMED", document_id, f"문서 {document_id}에 적힌 조회 시작일·종료일이 출처 조회 범위 및 신고기간과 맞는지 확인해 주세요.", source=source, documents=[document_id]))

    range_message = _source_range_issue(source, check, start, end)
    if range_message:
        issues.append(_issue("SOURCE_SCOPE_INCOMPLETE", source, range_message, source=source, documents=[document_id]))
    rows = evidence.get("내역") or []
    if not isinstance(rows, list) or not rows:
        issues.append(_issue("SOURCE_ROWS_MISSING", document_id, f"문서 {document_id}에서 매출 내역을 찾지 못했습니다. 조회 결과 또는 해당 없음 여부를 확인해 주세요.", source=source, documents=[document_id]))
        return []

    output: list[dict[str, Any]] = []
    original_rows = ((_saved_document(doc, doc.raw_prediction_json).get("매출증빙") or {}).get("내역") or []
                     if doc.contract_version.startswith("hometax-spreadsheet-") else [])
    for index, raw in enumerate(rows):
        if not isinstance(raw, dict):
            continue
        raw_scope = raw.get("범위")
        scope = {"건별": "detail", "집계": "monthly", "합계": "summary"}.get(raw_scope)
        ref = {"document": document_id, "row": index}
        if index < len(original_rows) and raw != original_rows[index]:
            ref["row_hash"] = _fingerprint(raw)
        if scope is None:
            issues.append(_issue("DATA_SCOPE_UNCLEAR", ref, f"문서 {document_id} {index + 1}행이 건별·월별 집계·상위 합계 중 무엇인지 확인해 주세요.", source=source, documents=[document_id], row=index))
            continue
        preferred_date = raw.get(document_basis) if document_basis in {"작성일", "발급일", "전송일"} else None
        row_date_value = preferred_date or raw.get("일자또는월") or raw.get("작성일") or raw.get("발급일") or raw.get("전송일")
        when, when_kind = _row_date(row_date_value)
        if when_kind == "invalid":
            issues.append(_issue("ROW_PERIOD_INVALID", ref, f"문서 {document_id} {index + 1}행의 일자·월을 확인해 주세요.", source=source, documents=[document_id], row=index))
            continue
        if when is None and scope != "summary":
            issues.append(_issue("ROW_PERIOD_MISSING", ref, f"문서 {document_id} {index + 1}행이 신고기간 안의 자료인지 확인해 주세요.", source=source, documents=[document_id], row=index))
            continue
        if when is not None and not start <= when < end:
            if pg_sheet:
                issues.append(_issue("PG_OUTSIDE_FILING_PERIOD", ref,
                    f"문서 {document_id} {index + 1}행의 승인월이 신고기간 밖입니다. 해당 기간으로 조회한 파일을 연결해 주세요.",
                    source=source, documents=[document_id], row=index, impact=raw.get("합계금액")))
            if invoice_list:
                issues.append(_issue("INVOICE_OUTSIDE_FILING_PERIOD", ref,
                    f"문서 {document_id} {index + 1}행의 작성일이 신고기간 밖입니다. 홈택스에서 해당 반기만 다시 내려받아 주세요.",
                    source=source, documents=[document_id], row=index, impact=raw.get("합계금액")))
            # Monthly evidence outside the filing period is recorded but not included.
            continue
        if invoice_list:
            category = raw.get("전자세금계산서분류")
            if _digits(raw.get("공급자사업자번호")) != expected_number:
                issues.append(_issue("INVOICE_SUPPLIER_MISMATCH", ref, "세금계산서 공급자가 신고 사업장과 다릅니다.",
                    source=source, documents=[document_id], row=index))
                continue
            if category not in {"세금계산서", "수정세금계산서"} or (
                category == "수정세금계산서" and (raw.get("합계금액") or 0) >= 0
            ):
                issues.append(_issue("INVOICE_CLASSIFICATION_REQUIRED", ref,
                    "문서 분류 또는 양수 수정세금계산서의 원거래를 확인해 주세요.",
                    source=source, documents=[document_id], row=index, impact=raw.get("합계금액")))
                continue
        card_sheet = source == "hometax_card" and "구매전용카드금액" in raw
        if card_sheet:
            exempt = raw.get("비과세금액")
            if (
                raw.get("자료구분") != "신용카드 자료"
                or raw.get("구매전용카드금액") != 0
                or not isinstance(exempt, int)
                or exempt < 0
            ):
                issues.append(_issue("CARD_SPREADSHEET_CLASSIFICATION_REQUIRED", ref,
                    f"문서 {document_id} {index + 1}행의 카드 자료구분·구매전용카드·비과세 금액을 확인해 주세요.",
                    source=source, documents=[document_id], row=index, impact=raw.get("합계금액")))
                continue
        if source == "hometax_cash_receipt" and document_basis == "거래년월" and raw.get("봉사료") is None:
            issues.append(_issue("CASH_SUMMARY_FEE_UNCONFIRMED", ref,
                f"문서 {document_id} {index + 1}행의 봉사료가 비어 있습니다. 원본에서 금액을 확인해 주세요.",
                source=source, documents=[document_id], row=index, impact=raw.get("합계금액")))
            continue
        treatment = (raw.get("과세구분") or "").strip()
        pg_amounts = None
        if pg_sheet:
            gross = raw["합계금액"]
            if gross == 0 and raw["건수"] == 0:
                continue
            if gross <= 0:
                issues.append(_issue("PG_NET_AMOUNT_REVIEW", ref,
                    f"문서 {document_id} {index + 1}행의 취소·환불과 원거래를 대조해 주세요.",
                    source=source, documents=[document_id], row=index, impact=gross))
                continue
            input_key = f"document:{document_id}:{index}"
            issue = _issue("PG_SPREADSHEET_RECONCILIATION_REQUIRED", {**ref, "row_hash": _fingerprint(raw)},
                f"{row_date_value} {raw['업체명']} {gross:,}원의 카드·현금영수증·세금계산서 반영 여부를 대조해 주세요. 누락분만 결제 구분과 금액을 확인해 반영합니다.",
                source=source, documents=[document_id], row=index, input_key=input_key, impact=gross)
            issue["pg_classification_confirmed"] = treatment in TAXABLE_VALUES and raw.get("결제수단") in PG_PAYMENTS
            resolution = resolutions.get(issue["issue_id"], {})
            if resolution.get("action") == "중복 확인" and resolution.get("amount") == gross:
                continue
            corrected = tuple(resolution.get(key) for key in ("supply_amount", "vat_amount", "total_amount"))
            if (resolution.get("action") != "누락 확인" or not issue["pg_classification_confirmed"]
                or not all(isinstance(value, int) and value >= 0 for value in corrected)
                or not 0 < corrected[2] <= gross or corrected[0] + corrected[1] != corrected[2]
                or corrected[1] != corrected[0] * STANDARD_RATE // 100):
                issues.append(issue)
                continue
            pg_amounts = corrected
        cash_summary = source == "hometax_cash_receipt" and document_basis == "거래년월"
        cash_amounts_confirmed = cash_summary and isinstance(raw.get("부가세"), int) and (
            raw["부가세"] != 0 or raw.get("합계금액") == raw.get("공급가액") == raw["부가세"] == 0
        )
        if treatment not in TAXABLE_VALUES and not ((card_sheet or cash_amounts_confirmed) and not treatment):
            issues.append(_issue("OUT_OF_SCOPE_TAX_TREATMENT", ref, f"문서 {document_id} {index + 1}행에 면세·영세율 또는 미확인 과세 구분이 있습니다. 해당 자료를 검토해 주세요.", source=source, documents=[document_id], row=index, impact=raw.get("합계금액")))
            continue
        if (raw.get("비과세금액") or 0) > 0 or (raw.get("봉사료") or 0) > 0:
            impact = (raw.get("비과세금액") or 0) + (raw.get("봉사료") or 0)
            issues.append(_issue("OUT_OF_SCOPE_NON_TAXABLE_COMPONENT", ref, f"문서 {document_id} {index + 1}행에 비과세 금액 또는 봉사료 {impact:,}원이 포함돼 있어 별도 검토가 필요합니다.", source=source, documents=[document_id], row=index, impact=impact))
            continue
        cancellation = raw.get("취소환불액") or 0
        trade_kind = (raw.get("거래구분") or "").strip()
        raw_total = raw.get("합계금액")
        is_cancellation = bool(cancellation) or "취소" in trade_kind or "환불" in trade_kind or (isinstance(raw_total, int) and raw_total < 0)
        cancellation_issue = _issue(
            "CANCELLATION_RECONCILIATION_REQUIRED", ref,
            f"문서 {document_id} {index + 1}행의 취소·환불 {abs(cancellation or raw_total or 0):,}원이 원거래와 같은 신고기간인지, 이미 순액에 반영됐는지 확인해 주세요.",
            source=source, documents=[document_id], row=index, impact=abs(cancellation or raw_total or 0),
        ) if is_cancellation else None
        resolution = resolutions.get(cancellation_issue["issue_id"]) if cancellation_issue else None
        values = pg_amounts if pg_sheet else _amounts(raw, allow_negative=is_cancellation)
        if is_cancellation and resolution and resolution.get("action") == "금액 정정":
            corrected = (resolution.get("supply_amount"), resolution.get("vat_amount"), resolution.get("total_amount"))
            all_nonnegative = all(isinstance(amount, int) and amount >= 0 for amount in corrected)
            all_nonpositive = all(isinstance(amount, int) and amount <= 0 for amount in corrected)
            original_reference = (resolution.get("original_reference") or raw.get("원승인번호") or "").strip()
            raw_original = (raw.get("원승인번호") or "").strip()
            original_period = (resolution.get("original_period") or "").strip()
            if not original_reference or original_period != period:
                issues.append(_issue("CANCELLATION_ORIGINAL_UNCONFIRMED", ref,
                    f"문서 {document_id} {index + 1}행의 원승인번호와 원거래 신고기간을 확인해 주세요. 다른 신고기간의 환불은 별도 검토가 필요합니다.",
                    source=source, documents=[document_id], row=index, impact=abs(cancellation or raw_total or 0)))
                continue
            if (all_nonnegative or all_nonpositive) and corrected[0] + corrected[1] == corrected[2]:
                values = corrected
            else:
                issues.append(_issue("CORRECTED_AMOUNT_INVALID", ref, f"문서 {document_id} {index + 1}행의 정정 금액이 맞지 않습니다.", source=source, documents=[document_id], row=index))
                continue
        elif is_cancellation:
            issues.append(cancellation_issue)
        if values is None:
            code = "CANCELLATION_RECONCILIATION_REQUIRED" if is_cancellation else "AMOUNT_COMPONENT_MISMATCH"
            message = cancellation_issue["question"] if is_cancellation else f"문서 {document_id} {index + 1}행의 공급가액·세액·공급대가가 맞는지 확인해 주세요."
            issues.append(_issue(code, ref, message, source=source, documents=[document_id], row=index, impact=abs(raw_total or 0)))
            continue
        supply, vat, total = values
        card_part, other_part = raw.get("카드금액"), raw.get("기타결제금액")
        if not pg_sheet and (card_part is not None or other_part is not None) and (card_part or 0) + (other_part or 0) != total:
            issues.append(_issue("PAYMENT_COMPONENT_MISMATCH", ref, f"문서 {document_id} {index + 1}행의 카드·기타 결제 구성액이 합계 {total:,}원과 맞는지 확인해 주세요.", source=source, documents=[document_id], row=index, impact=total))
            continue
        if vat != supply * STANDARD_RATE // 100:
            issues.append(_issue("STANDARD_RATE_MISMATCH", ref, f"문서 {document_id} {index + 1}행은 공급가액의 10%와 세액이 다릅니다. 과세 구분과 금액을 확인해 주세요.", source=source, documents=[document_id], row=index, impact=total))
        payment_method = (raw.get("결제수단") or "").lower()
        line_number = 1 if source == "hometax_sales_invoice" else 3 if source in CARD_SOURCES or any(token in payment_method for token in ("카드", "현금영수증", "card")) else 4
        normalized_row = {
            "source": source, "line": line_number,
            "document_id": document_id, "row_index": index,
            "document_period_start": doc_range_start, "document_period_end": doc_range_end,
            "file_sha256": doc.image_sha256,
            "lookup_start": check.get("query_start"), "lookup_end": check.get("query_end"),
            "basis": check.get("basis"), "scope": scope,
            "date": row_date_value, "reference": _evidence_reference(raw),
            "label": raw.get("원문항목") or SOURCE_LABELS[source],
            "supply_amount": supply, "vat_amount": vat, "total_amount": total,
            "fee_amount": raw.get("수수료"), "deposit_amount": raw.get("실입금액"),
            "refund_amount": cancellation,
            "original_reference": resolution.get("original_reference") if resolution else raw.get("원승인번호"),
            "original_period": resolution.get("original_period") if resolution else None,
            "raw_row": raw,
        }
        if "row_hash" in ref:
            normalized_row["spreadsheet_review_hash"] = ref["row_hash"]
        if pg_sheet:
            normalized_row["input_key"] = input_key
            normalized_row["pg_sheet_key"] = (row_date_value, re.sub(r"\s+", "", raw["업체명"]).casefold())
        elif source in {"pg", "unissued_sales"}:
            input_key = f"document:{document_id}:{index}"
            normalized_row["input_key"] = input_key
            issue = _issue(
                "PG_RECONCILIATION_REQUIRED" if source == "pg" else "UNISSUED_SALE_CONFIRMATION_REQUIRED",
                input_key,
                (f"문서 {document_id} {index + 1}행의 PG·플랫폼 매출 {total:,}원이 홈택스 자료에 포함됐는지 확인해 주세요."
                 if source == "pg" else f"문서 {document_id} {index + 1}행의 미발급 매출 {total:,}원이 실제 공급이고 신고자료에서 빠졌는지 확인해 주세요."),
                source=source, documents=[document_id], row=index, input_key=input_key, impact=total,
            )
            resolution = resolutions.get(issue["issue_id"])
            if resolution is None:
                issues.append(issue)
                continue
            if resolution.get("action") in {"중복 확인", "해당 없음"}:
                continue
            if resolution.get("action") != "누락 확인":
                issues.append(issue)
                continue
            if resolution.get("supply_amount") is not None:
                corrected = (resolution.get("supply_amount"), resolution.get("vat_amount"), resolution.get("total_amount"))
                if all(isinstance(amount, int) and amount >= 0 for amount in corrected) and corrected[0] + corrected[1] == corrected[2] and corrected[1] == corrected[0] * STANDARD_RATE // 100:
                    normalized_row["supply_amount"], normalized_row["vat_amount"], normalized_row["total_amount"] = corrected
                else:
                    issues.append(_issue("CORRECTED_AMOUNT_INVALID", input_key, f"문서 {document_id} {index + 1}행의 정정 금액을 확인해 주세요.", source=source, documents=[document_id], row=index, input_key=input_key))
                    continue
        output.append(normalized_row)
    return output


def _manual_rows(case: SalesFilingWorkflow, resolutions: dict[str, dict[str, Any]], issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for item in _loads(case.manual_inputs_json, []):
        source = item.get("source")
        input_key = item.get("input_key")
        issue = _issue(
            "PG_RECONCILIATION_REQUIRED" if source == "pg" else "UNISSUED_SALE_CONFIRMATION_REQUIRED",
            input_key,
            (f"{item.get('date') or '신고기간'} PG·플랫폼 매출 {item.get('total_amount') or 0:,}원이 홈택스에 포함됐는지 확인해 주세요."
             if source == "pg" else f"{item.get('date') or '신고기간'} 현금·계좌이체 공급 {item.get('total_amount') or item.get('supply_amount') or 0:,}원이 실제 공급이고 신고자료에 빠졌는지 확인해 주세요."),
            source=source, input_key=input_key, impact=item.get("total_amount"),
        )
        resolution = resolutions.get(issue["issue_id"])
        if resolution is None:
            issues.append(issue)
            continue
        action = resolution.get("action")
        if action in {"중복 확인", "해당 없음"}:
            continue
        if action != "누락 확인":
            issues.append(issue)
            continue
        tax_treatment = (item.get("tax_treatment") or "").strip()
        if tax_treatment not in TAXABLE_VALUES:
            issues.append(_issue("OUT_OF_SCOPE_TAX_TREATMENT", input_key, f"{SOURCE_LABELS[source]} 입력 {input_key}에 면세·영세율 또는 미확인 과세 구분이 있어 검토가 필요합니다.", source=source, input_key=input_key, impact=item.get("total_amount")))
            continue
        values = (item.get("supply_amount"), item.get("vat_amount"), item.get("total_amount"))
        if resolution.get("supply_amount") is not None:
            values = (resolution.get("supply_amount"), resolution.get("vat_amount"), resolution.get("total_amount"))
        supply, vat, total = values
        if total is None and supply is not None:
            vat = vat if vat is not None else supply * STANDARD_RATE // 100
            total = supply + vat
        if supply is None and total is not None:
            supply = (int(total) * 100 + 55) // 110
        if vat is None and supply is not None and total is not None:
            vat = total - supply
        if any(not isinstance(value, int) or value < 0 for value in (supply, vat, total)) or supply + vat != total:
            issues.append(_issue("MANUAL_AMOUNT_INVALID", input_key, f"{SOURCE_LABELS[source]} 입력 {input_key}의 공급가액·세액·공급대가를 확인해 주세요.", source=source, input_key=input_key, impact=total))
            continue
        if vat != supply * STANDARD_RATE // 100:
            issues.append(_issue("STANDARD_RATE_MISMATCH", input_key, f"{SOURCE_LABELS[source]} 입력 {input_key}은 공급가액의 10%와 세액이 다릅니다.", source=source, input_key=input_key, impact=total))
            continue
        payment = (item.get("payment_method") or "").lower()
        line = 3 if source == "pg" and any(token in payment for token in ("card", "카드", "현금영수증")) else 4
        result.append({
            "source": source, "line": line, "document_id": None, "row_index": None,
            "input_key": input_key, "date": item.get("date"), "reference": item.get("reference"),
            "label": item.get("description") or SOURCE_LABELS[source], "scope": "confirmed_manual",
            "lookup_start": None, "lookup_end": None, "basis": "사용자 확인",
            "supply_amount": supply, "vat_amount": vat, "total_amount": total,
            "fee_amount": item.get("fee_amount"), "deposit_amount": item.get("deposit_amount"),
            "refund_amount": 0, "raw_row": item,
        })
    return result


def _row_signature(row: dict[str, Any]) -> str:
    return _fingerprint({key: row.get(key) for key in (
        "source", "lookup_start", "lookup_end", "document_period_start", "document_period_end", "scope", "date", "reference", "label",
        "supply_amount", "vat_amount", "total_amount",
    )})


def _duplicate_reference(row: dict[str, Any]) -> str | None:
    value = row.get("reference")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _apply_cross_source_duplicates(
    rows: list[dict[str, Any]], resolutions: dict[str, dict[str, Any]], issues: list[dict[str, Any]], deduplicated: list[dict[str, Any]],
) -> None:
    invoices = [row for row in rows if row["source"] == "hometax_sales_invoice"]
    cards = [row for row in rows if row["source"] in CARD_SOURCES]
    removed: dict[int, int] = {}
    pairs: set[tuple[str, str]] = set()
    for invoice in invoices:
        for card in cards:
            invoice_ref = _duplicate_reference(invoice)
            card_ref = _duplicate_reference(card)
            same_period = bool(invoice.get("date") and card.get("date") and invoice["date"][:7] == card["date"][:7])
            same_amount = invoice["total_amount"] == card["total_amount"]
            same_ref = bool(invoice_ref and card_ref and invoice_ref == card_ref)
            if not same_ref and not (same_period and same_amount):
                continue
            pair_key = tuple(sorted((f"{invoice.get('document_id')}:{invoice.get('row_index')}", f"{card.get('document_id')}:{card.get('row_index')}")))
            if pair_key in pairs:
                continue
            pairs.add(pair_key)
            key = {"invoice": pair_key[0], "card": pair_key[1]}
            if invoice.get("spreadsheet_review_hash") or card.get("spreadsheet_review_hash"):
                key["review"] = [invoice.get("spreadsheet_review_hash"), card.get("spreadsheet_review_hash")]
            duplicate_issue = _issue(
                "POSSIBLE_INVOICE_CARD_DUPLICATE", key,
                f"세금계산서와 카드·현금영수증 자료가 같은 공급인지 확인해 주세요. 두 자료 합계는 {min(invoice['total_amount'], card['total_amount']):,}원입니다. 승인·주문·증빙번호를 확인하고 중복액 또는 해당 없음으로 답해 주세요.",
                source="hometax_sales_invoice", documents=[invoice["document_id"], card["document_id"]],
                row=card["row_index"], impact=min(invoice["total_amount"], card["total_amount"]),
            )
            if same_ref and same_amount:
                removed[id(card)] = card["total_amount"]
                deduplicated.append({"reason": "같은 승인·주문·증빙번호", "source_document": card["document_id"], "source_row": card["row_index"], "excluded_total_amount": card["total_amount"]})
                continue
            resolution = resolutions.get(duplicate_issue["issue_id"])
            if resolution is None:
                issues.append(duplicate_issue)
            elif resolution.get("action") == "중복 확인":
                amount = resolution.get("amount")
                amount = min(invoice["total_amount"], card["total_amount"]) if amount is None else amount
                if isinstance(amount, int) and 0 < amount <= card["total_amount"]:
                    removed[id(card)] = min(card["total_amount"], removed.get(id(card), 0) + amount)
                    deduplicated.append({"reason": "사용자가 확인한 세금계산서·카드 중복", "source_document": card["document_id"], "source_row": card["row_index"], "excluded_total_amount": amount})
                else:
                    issues.append(_issue("DUPLICATE_AMOUNT_INVALID", key, "확인한 중복액이 카드·현금영수증 금액 범위 안인지 확인해 주세요.", source="hometax_sales_invoice", documents=[invoice["document_id"], card["document_id"]], row=card["row_index"], impact=card["total_amount"]))
            elif resolution.get("action") != "해당 없음":
                issues.append(duplicate_issue)

    for row in rows:
        amount = removed.get(id(row), 0)
        if not amount:
            continue
        if amount >= row["total_amount"]:
            row["supply_amount"] = row["vat_amount"] = row["total_amount"] = 0
        else:
            remaining_total = row["total_amount"] - amount
            remaining_supply = max(0, (row["supply_amount"] * remaining_total + row["total_amount"] // 2) // row["total_amount"])
            row["total_amount"] = remaining_total
            row["supply_amount"] = remaining_supply
            row["vat_amount"] = remaining_total - remaining_supply


def _deduplicate_and_choose_scope(
    rows: list[dict[str, Any]], resolutions: dict[str, dict[str, Any]], issues: list[dict[str, Any]], deduplicated: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    seen_references: dict[tuple[str, str | None, str | None, str], dict[str, Any]] = {}
    pg_rows: dict[tuple[str, str], dict[str, Any]] = {}
    unique: list[dict[str, Any]] = []
    for row in rows:
        pg_key = row.get("pg_sheet_key")
        if pg_key:
            previous_pg = pg_rows.get(pg_key)
            if previous_pg:
                issues.append(_issue("PG_DUPLICATE_MONTH_PROVIDER", pg_key,
                    f"{row['date']} {row['label']} 자료가 여러 파일에 있습니다. 원본을 대조하고 하나만 연결해 주세요.",
                    source="pg", documents=[previous_pg["document_id"], row["document_id"]], impact=row["total_amount"]))
                continue
            pg_rows[pg_key] = row
        signature = _row_signature(row)
        previous = seen.get(signature)
        if previous:
            reference = _duplicate_reference(row)
            if reference:
                deduplicated.append({"reason": "다른 파일에 포함된 동일 출처·범위·증빙번호의 동일 자료", "source_document": row.get("document_id"), "source_row": row.get("row_index"), "duplicate_of": {"document_id": previous.get("document_id"), "row_index": previous.get("row_index")}, "excluded_total_amount": row["total_amount"]})
                continue
            if previous.get("document_id") == row.get("document_id"):
                # Identical-looking detail rows in one report can still be separate sales.
                unique.append(row)
                continue
            duplicate_key = sorted((f"{previous.get('document_id')}:{previous.get('row_index')}", f"{row.get('document_id')}:{row.get('row_index')}"))
            review_hashes = [previous.get("spreadsheet_review_hash"), row.get("spreadsheet_review_hash")]
            possible_duplicate = _issue(
                "POSSIBLE_SAME_SOURCE_DUPLICATE", {"rows": duplicate_key, "review": review_hashes} if any(review_hashes) else duplicate_key,
                f"서로 다른 파일의 {SOURCE_LABELS[row['source']]} 자료에서 같은 조회범위·기간·구분·일자·항목·금액 {row['total_amount']:,}원이 확인됐습니다. 같은 증빙인지 승인번호·주문번호 또는 원자료로 확인해 주세요.",
                source=row.get("source"), documents=list(dict.fromkeys([previous.get("document_id"), row.get("document_id")])),
                row=row.get("row_index"), impact=row["total_amount"],
            )
            resolution = resolutions.get(possible_duplicate["issue_id"])
            if resolution is None:
                issues.append(possible_duplicate)
                unique.append(row)
                continue
            if resolution.get("action") == "중복 확인":
                if resolution.get("amount") == row["total_amount"]:
                    deduplicated.append({"reason": "사용자가 확인한 다른 파일의 동일 출처 매출", "source_document": row.get("document_id"), "source_row": row.get("row_index"), "duplicate_of": {"document_id": previous.get("document_id"), "row_index": previous.get("row_index")}, "excluded_total_amount": row["total_amount"]})
                    continue
                issues.append(_issue("DUPLICATE_AMOUNT_INVALID", duplicate_key, "중복으로 확인한 금액이 중복 행 전체 금액과 같은지 확인해 주세요.", source=row.get("source"), documents=list(dict.fromkeys([previous.get("document_id"), row.get("document_id")])), row=row.get("row_index"), impact=row["total_amount"]))
                unique.append(row)
                continue
            if resolution.get("action") != "해당 없음":
                issues.append(possible_duplicate)
            unique.append(row)
            continue
        reference = _duplicate_reference(row)
        reference_key = (row.get("source"), row.get("lookup_start"), row.get("lookup_end"), reference) if reference else None
        if reference_key and reference_key in seen_references:
            previous_reference = seen_references[reference_key]
            if all(previous_reference.get(key) == row.get(key) for key in ("supply_amount", "vat_amount", "total_amount")):
                deduplicated.append({"reason": "같은 출처 조회범위의 동일 승인·주문·증빙번호", "source_document": row.get("document_id"), "source_row": row.get("row_index"), "duplicate_of": {"document_id": previous_reference.get("document_id"), "row_index": previous_reference.get("row_index")}, "excluded_total_amount": row["total_amount"]})
            else:
                issues.append(_issue("DUPLICATE_REFERENCE_CONFLICT", reference_key,
                    f"같은 승인·주문·증빙번호({reference})의 금액이 자료 사이에서 다릅니다. 실제 금액과 중복 범위를 확인해 주세요.",
                    source=row.get("source"), documents=list(dict.fromkeys([previous_reference.get("document_id"), row.get("document_id")])), row=row.get("row_index"), impact=row["total_amount"]))
            continue
        seen[signature] = row
        if reference_key:
            seen_references[reference_key] = row
        unique.append(row)

    totals = [row for row in unique if row.get("scope") == "summary" and row.get("document_id") is not None]
    skip_ids: set[int] = set()
    for total in totals:
        components = [row for row in unique if row.get("source") == total.get("source")
                      and row.get("lookup_start") == total.get("lookup_start")
                      and row.get("lookup_end") == total.get("lookup_end")
                      and row.get("scope") != "summary" and row.get("document_id") is not None]
        total_payment = ((total.get("raw_row") or {}).get("결제수단") or "").strip()
        if total_payment:
            same_payment = [row for row in components if (((row.get("raw_row") or {}).get("결제수단") or "").strip() == total_payment)]
            if same_payment:
                components = same_payment
        if not components:
            continue
        components_total = sum(row["total_amount"] for row in components)
        scope_key = {"total": [total.get("document_id"), total.get("row_index")],
                     "components": [[r.get("document_id"), r.get("row_index")] for r in components]}
        review_hashes = [row.get("spreadsheet_review_hash") for row in [total, *components]]
        if any(review_hashes):
            scope_key["review"] = review_hashes
        issue = _issue(
            "OVERLAPPING_TOTAL_AND_COMPONENTS", scope_key,
            f"같은 {SOURCE_LABELS[total['source']]} 조회 범위의 상위 합계 {total['total_amount']:,}원과 월별·상세 구성행 {components_total:,}원이 겹치는지 확인해 주세요.",
            source=total["source"], documents=list(dict.fromkeys([total["document_id"], *[r["document_id"] for r in components]])),
            row=total.get("row_index"), impact=total["total_amount"],
        )
        if total["total_amount"] == components_total:
            skip_ids.add(id(total))
            deduplicated.append({"reason": "상위 합계가 월별·상세 구성행 합과 일치", "source_document": total["document_id"], "source_row": total["row_index"], "excluded_total_amount": total["total_amount"]})
            continue
        resolution = resolutions.get(issue["issue_id"])
        if resolution is None:
            issues.append(issue)
            # Do not count both sides while the range is unresolved.
            skip_ids.add(id(total))
        elif resolution.get("action") == "중복 확인":
            skip_ids.add(id(total))
            deduplicated.append({"reason": "사용자가 확인한 상위 합계·구성행 중복", "source_document": total["document_id"], "source_row": total.get("row_index"), "excluded_total_amount": total["total_amount"]})
        elif resolution.get("action") != "해당 없음":
            issues.append(issue)

    return [row for row in unique if id(row) not in skip_ids]


def _build_result(
    session: Session, case: SalesFilingWorkflow, profile: BusinessProfile | None, tax_profile: TaxProfileV2 | None,
    source_checks: dict[str, dict[str, Any]], documents: dict[int, MonthlySalesDocument],
    missing_document_ids: list[dict[str, Any]], start: date, end: date,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    resolutions = _resolution_map(case)
    if profile is None:
        issues.append(_issue("BUSINESS_PROFILE_MISSING", case.period, "일반과세 사업장 정보를 확인해 주세요."))
    elif profile.tax_type_code != "01":
        issues.append(_issue("UNSUPPORTED_TAXPAYER", case.period, "이 매출 집계는 일반과세자 1사업장만 지원합니다. 과세유형을 확인해 주세요."))
    if tax_profile is None or tax_profile.confirmed_at is None or tax_profile.entity_type != "individual":
        issues.append(_issue("BUSINESS_ENTITY_UNCONFIRMED", case.period, "개인사업자 여부가 확인된 사업자 정보를 입력해 주세요."))
    if profile and not _digits(profile.business_number):
        issues.append(_issue("BUSINESS_NUMBER_MISSING", case.period, "사업자등록번호를 확인해 주세요."))

    for item in missing_document_ids:
        document_id = item["document_id"]
        issues.append(_issue("SOURCE_DOCUMENT_NOT_FOUND", document_id, f"선택한 매출자료 문서 {document_id}를 찾을 수 없습니다. 문서를 다시 선택해 주세요.", documents=[document_id]))

    for source in SOURCES:
        check = source_checks[source]
        status = check.get("status", "자료 없음")
        if status not in SOURCE_STATUSES:
            issues.append(_issue("SOURCE_STATUS_INVALID", source, f"{SOURCE_LABELS[source]} 자료 상태를 다시 선택해 주세요.", source=source))
        elif status == "자료 없음":
            issues.append(_issue("SOURCE_MISSING", source, f"{case.period} {SOURCE_LABELS[source]} 자료가 없습니다. 자료를 추가하거나 해당 없음인지 확인해 주세요.", source=source))
        elif status == "검토 필요":
            issues.append(_issue("SOURCE_NEEDS_REVIEW", source, f"{SOURCE_LABELS[source]} 자료에 unresolved 검토 항목이 있습니다. 근거를 확인해 주세요.", source=source, documents=check.get("document_ids", [])))
        elif status == "해당 없음 확인" and (check.get("document_ids") or any(item.get("source") == source for item in _loads(case.manual_inputs_json, []))):
            issues.append(_issue("SOURCE_NOT_APPLICABLE_CONFLICT", source, f"{SOURCE_LABELS[source]}를 해당 없음으로 표시했지만 연결된 자료가 있습니다. 자료 상태를 다시 확인해 주세요.", source=source, documents=check.get("document_ids", [])))
        elif status == "확인 완료":
            if source in HOMETAX_SOURCES:
                range_message = _source_range_issue(source, check, start, end)
                if range_message:
                    issues.append(_issue("SOURCE_SCOPE_INCOMPLETE", source, range_message, source=source, documents=check.get("document_ids", [])))
                if not check.get("document_ids"):
                    issues.append(_issue("SOURCE_EVIDENCE_MISSING", source, f"{SOURCE_LABELS[source]} 조회 범위를 확인했지만 연결된 자료가 없습니다. 파일 또는 조회 결과를 추가해 주세요.", source=source))
            elif source == "pg":
                range_message = _source_range_issue(source, check, start, end)
                if range_message:
                    issues.append(_issue("SOURCE_SCOPE_INCOMPLETE", source, range_message, source=source, documents=check.get("document_ids", [])))
                if not check.get("document_ids") and not any(item.get("source") == source for item in _loads(case.manual_inputs_json, [])):
                    issues.append(_issue("SOURCE_EVIDENCE_MISSING", source, "PG·플랫폼 자료를 확인 완료로 표시했지만 비교 자료가 없습니다. 자료를 추가하거나 해당 없음인지 확인해 주세요.", source=source))
            elif source == "unissued_sales":
                if not check.get("document_ids") and not any(item.get("source") == source for item in _loads(case.manual_inputs_json, [])):
                    issues.append(_issue("SOURCE_EVIDENCE_MISSING", source, "미발급 매출을 확인 완료로 표시했지만 확인 근거가 없습니다. 매출장 또는 증빙을 추가해 주세요.", source=source))

    rows: list[dict[str, Any]] = []
    for source in SOURCES:
        check = source_checks[source]
        for document_id in dict.fromkeys(check.get("document_ids", [])):
            doc = documents.get(document_id)
            if doc is None:
                continue
            rows.extend(_normalize_document_rows(
                source=source, document_id=document_id, doc=doc, check=check,
                profile=profile, start=start, end=end, period=case.period, resolutions=resolutions, issues=issues,
            ))

    rows.extend(_manual_rows(case, resolutions, issues))
    deduplicated: list[dict[str, Any]] = []
    rows = _deduplicate_and_choose_scope(rows, resolutions, issues, deduplicated)
    _apply_cross_source_duplicates(rows, resolutions, issues, deduplicated)

    totals = {line: {"supply_amount": 0, "vat_amount": 0, "total_amount": 0} for line in (1, 3, 4)}
    for row in rows:
        if row["line"] not in totals:
            continue
        for name in ("supply_amount", "vat_amount", "total_amount"):
            totals[row["line"]][name] += row[name]
    totals[9] = {name: sum(totals[line][name] for line in (1, 3, 4)) for name in ("supply_amount", "vat_amount", "total_amount")}
    totals[35] = {"tax_base": totals[9]["supply_amount"]}
    if totals[9]["supply_amount"] != totals[35]["tax_base"]:
        issues.append(_issue("RETURN_TAX_BASE_MISMATCH", case.period, "신고서 (9)와 (35)의 과세표준이 일치하지 않습니다."))

    # Keep the raw OCR row and source range beside every included amount for audit and feedback.
    aggregate = {
        "period": case.period,
        "business_number": _digits(profile.business_number if profile else None),
        "source_statuses": source_checks,
        "lines": {str(key): value for key, value in totals.items()},
        "included_rows": rows,
        "deduplicated_rows": deduplicated,
        "issue_count": len({item["issue_id"] for item in issues}),
        "basis": "확인 완료 홈택스 자료 + 누락 확인 PG·미발급 매출",
    }
    return aggregate, issues


def refresh(session: Session, user: User, period: str) -> SalesFilingWorkflow:
    start, end = _period_dates(period)
    case = _case(session, user.id, period)
    profile = _profile(session, user.id)
    tax_profile = _tax_profile(session, user.id)
    checks = _default_checks()
    checks.update(_loads(case.source_checks_json, {}))
    manual_inputs = _loads(case.manual_inputs_json, [])
    feedback = _loads(case.feedback_json, [])
    documents, missing_ids = _selected_documents(session, checks, user.id)
    document_observation = {
        str(document_id): {
            "sha256": doc.image_sha256,
            "review_sha256": _fingerprint(_saved_document(doc, doc.review_json)),
            "status": doc.status,
            "deleted_at": doc.deleted_at.isoformat() if doc.deleted_at else None,
            "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
        }
        for document_id, doc in sorted(documents.items())
    }
    profile_observation = {
        "business_number": profile.business_number if profile else None,
        "tax_type_code": profile.tax_type_code if profile else None,
    }
    fingerprint = _fingerprint({
        "period": period, "profile": profile_observation, "checks": checks,
        "inputs": manual_inputs, "feedback": feedback, "documents": document_observation,
        "missing_document_ids": missing_ids,
    })
    changed_after_confirmation = case.status == "확정" and case.input_fingerprint != fingerprint
    if changed_after_confirmation:
        history = _loads(case.history_json, [])
        history.append({
            "revision": case.revision,
            "finalized_at": case.finalized_at.isoformat() if case.finalized_at else None,
            "input_fingerprint": case.input_fingerprint,
            "aggregate": _loads(case.aggregate_json, {}),
            "source_checks": _loads(case.aggregate_json, {}).get("source_statuses", _loads(case.source_checks_json, {})),
        })
        case.history_json = _json(history)
        case.status = "검토 필요"
        case.reconfirmation_required = True
        case.finalized_at = None

    aggregate, issues = _build_result(session, case, profile, tax_profile, checks, documents, missing_ids, start, end)
    if case.reconfirmation_required and not issues:
        issues.append(_issue("CONFIRMED_INPUT_CHANGED", fingerprint,
                             "확정 이후 매출 근거가 바뀌었습니다. 새 집계와 근거를 검토한 뒤 다시 확정해 주세요."))
    issue_ids = {item["issue_id"] for item in issues}
    if changed_after_confirmation or case.input_fingerprint != fingerprint or _loads(case.aggregate_json, {}) != aggregate or _loads(case.issues_json, []) != issues:
        case.revision += 1
    case.business_number = _digits(profile.business_number if profile else None)
    case.source_checks_json = _json(checks)
    case.aggregate_json = _json(aggregate)
    case.issues_json = _json(issues)
    case.input_fingerprint = fingerprint
    if issue_ids:
        case.status = "검토 필요"
    elif case.status != "확정":
        case.status = "확정 가능"
    case.updated_at = _now()
    session.add(case)
    session.commit()
    session.refresh(case)
    return case


def update_source(
    session: Session, user: User, period: str, source: str, *, status: str,
    query_start: date | None, query_end: date | None, basis: str | None,
    document_ids: list[int], reason: str | None, expected_document_ids: list[int] | None = None,
) -> SalesFilingWorkflow:
    _period_dates(period)
    if source not in SOURCES:
        raise AppException(400, "INVALID_SALES_SOURCE", "지원하지 않는 매출 자료 출처입니다.")
    if status not in SOURCE_STATUSES:
        raise AppException(400, "INVALID_SOURCE_STATUS", "출처 상태를 확인 완료·해당 없음 확인·자료 없음·검토 필요 중에서 선택해 주세요.")
    if status == "해당 없음 확인" and not (reason or "").strip():
        raise AppException(400, "SOURCE_REASON_REQUIRED", "해당 없음으로 확인한 근거를 입력해 주세요.")
    if status == "확인 완료" and source in HOMETAX_SOURCES and (query_start is None or query_end is None or not (basis or "").strip()):
        raise AppException(400, "SOURCE_SCOPE_REQUIRED", "홈택스 자료의 조회 시작일·종료일과 기준을 입력해 주세요.")
    ids = list(dict.fromkeys(document_ids))
    case = _case(session, user.id, period)
    checks = _default_checks()
    previous_checks = case.source_checks_json
    checks.update(_loads(previous_checks, {}))
    if expected_document_ids is not None:
        if checks[source].get("document_ids", []) != expected_document_ids:
            raise AppException(409, "SALES_SOURCE_CHANGED", "연결된 파일이 바뀌었습니다. 현재 연결 상태를 확인하고 다시 시도해 주세요.")
        if len(ids) != 1:
            raise AppException(400, "SALES_DOCUMENT_REQUIRED", "연결할 매출 파일 한 개를 선택해 주세요.")
        document = session.exec(select(MonthlySalesDocument).where(
            MonthlySalesDocument.id == ids[0], MonthlySalesDocument.user_id == user.id,
            MonthlySalesDocument.deleted_at.is_(None),
        )).first()
        evidence = (_loads(document.review_json, {}).get("매출증빙") or {}) if document else {}
        if not document or document.status != "reviewed" or evidence.get("문서유형") not in EXPECTED_DOC_TYPES[source]:
            raise AppException(400, "INVALID_SOURCE_DOCUMENT", "이 출처에 맞는 매출 자료를 저장한 뒤 연결해 주세요.")
    checks[source] = {
        "status": status,
        "query_start": query_start.isoformat() if query_start else None,
        "query_end": query_end.isoformat() if query_end else None,
        "basis": (basis or "").strip() or None,
        "document_ids": ids,
        "reason": (reason or "").strip() or None,
    }
    result = session.execute(update(SalesFilingWorkflow).where(
        SalesFilingWorkflow.id == case.id, SalesFilingWorkflow.source_checks_json == previous_checks,
    ).values(source_checks_json=_json(checks)))
    if result.rowcount != 1:
        session.rollback()
        raise AppException(409, "SALES_SOURCE_CHANGED", "연결 상태가 바뀌었습니다. 다시 시도해 주세요.")
    session.commit()
    return refresh(session, user, period)


def add_manual_input(session: Session, user: User, period: str, payload: dict[str, Any]) -> SalesFilingWorkflow:
    start, end = _period_dates(period)
    source = payload.get("source")
    if source not in {"pg", "unissued_sales"}:
        raise AppException(400, "INVALID_MANUAL_SALES_SOURCE", "수기 입력은 PG·플랫폼 또는 미발급 매출만 지원합니다.")
    input_key = (payload.get("input_key") or "").strip()
    if not input_key:
        raise AppException(400, "INPUT_KEY_REQUIRED", "중복 입력 방지를 위해 input_key가 필요합니다.")
    try:
        input_date = date.fromisoformat(payload.get("date") or "") if payload.get("date") else None
    except ValueError:
        raise AppException(400, "INVALID_SALES_DATE", "매출 일자를 확인해 주세요.") from None
    if input_date and not start <= input_date < end:
        raise AppException(400, "SALES_DATE_OUT_OF_PERIOD", "매출 일자가 신고기간 밖입니다.")
    for name in ("supply_amount", "vat_amount", "total_amount", "fee_amount", "deposit_amount"):
        amount = payload.get(name)
        if amount is not None and (not isinstance(amount, int) or amount < 0):
            raise AppException(400, "INVALID_SALES_AMOUNT", "매출·수수료·입금액은 0 이상의 원 단위로 입력해 주세요.")
    normalized = {
        "input_key": input_key, "source": source, "date": input_date.isoformat() if input_date else None,
        "description": (payload.get("description") or "").strip(), "reference": (payload.get("reference") or "").strip() or None,
        "payment_method": (payload.get("payment_method") or "").strip(), "tax_treatment": (payload.get("tax_treatment") or "").strip(),
        "supply_amount": payload.get("supply_amount"), "vat_amount": payload.get("vat_amount"), "total_amount": payload.get("total_amount"),
        "fee_amount": payload.get("fee_amount"), "deposit_amount": payload.get("deposit_amount"),
        "supporting_evidence": (payload.get("supporting_evidence") or "").strip(),
    }
    if not normalized["supporting_evidence"]:
        raise AppException(400, "SALES_EVIDENCE_REQUIRED", "매출이 실제 공급이고 신고자료와 대조할 수 있는 근거를 입력해 주세요.")
    case = _case(session, user.id, period)
    items = _loads(case.manual_inputs_json, [])
    existing = next((item for item in items if item.get("input_key") == input_key), None)
    if existing and existing != normalized:
        raise AppException(409, "INPUT_KEY_REUSED", "같은 input_key에는 처음 저장한 입력과 같은 내용을 보내야 합니다.")
    if existing is None:
        items.append(normalized)
        case.manual_inputs_json = _json(items)
        session.add(case)
        session.commit()
    return refresh(session, user, period)


def add_feedback(session: Session, user: User, period: str, payload: dict[str, Any]) -> SalesFilingWorkflow:
    case = refresh(session, user, period)
    request_id = (payload.get("request_id") or "").strip()
    issue_id = (payload.get("issue_id") or "").strip()
    action = payload.get("action")
    evidence = (payload.get("evidence") or "").strip()
    if not request_id or not issue_id:
        raise AppException(400, "FEEDBACK_ID_REQUIRED", "확인 요청마다 request_id와 issue_id를 입력해 주세요.")
    if action not in {"중복 확인", "누락 확인", "해당 없음", "금액 정정"}:
        raise AppException(400, "INVALID_FEEDBACK_ACTION", "중복 확인·누락 확인·해당 없음·금액 정정 중에서 선택해 주세요.")
    if not evidence:
        raise AppException(400, "FEEDBACK_EVIDENCE_REQUIRED", "사용자 확인 근거를 입력해 주세요.")
    issues = _loads(case.issues_json, [])
    issue = next((item for item in issues if item["issue_id"] == issue_id), None)
    if issue is None:
        # Repeat a previously saved request is an idempotent no-op even when it resolved its issue.
        saved = _loads(case.feedback_json, [])
        previous = next((item for item in saved if item.get("request_id") == request_id), None)
        if previous:
            incoming = {"request_id": request_id, "issue_id": issue_id, "action": action, "evidence": evidence,
                        "amount": payload.get("amount"), "supply_amount": payload.get("supply_amount"),
                        "vat_amount": payload.get("vat_amount"), "total_amount": payload.get("total_amount"),
                        "original_reference": payload.get("original_reference"),
                        "original_period": payload.get("original_period")}
            stored = {key: previous.get(key) for key in incoming}
            if incoming != stored:
                raise AppException(409, "FEEDBACK_KEY_REUSED", "같은 request_id에는 처음 저장한 확인 내용만 다시 보낼 수 있습니다.")
            return case
        raise AppException(404, "SALES_ISSUE_NOT_FOUND", "다시 검증한 결과에서 해당 매출 검토 항목을 찾지 못했습니다.")

    feedback = {
        "request_id": request_id, "issue_id": issue_id, "action": action, "evidence": evidence,
        "amount": payload.get("amount"), "supply_amount": payload.get("supply_amount"),
        "vat_amount": payload.get("vat_amount"), "total_amount": payload.get("total_amount"),
        "original_reference": payload.get("original_reference"),
        "original_period": payload.get("original_period"),
        "recorded_at": _now().isoformat(),
    }
    saved = _loads(case.feedback_json, [])
    previous = next((item for item in saved if item.get("request_id") == request_id), None)
    if previous:
        comparable = {key: value for key, value in feedback.items() if key != "recorded_at"}
        previous_comparable = {key: value for key, value in previous.items() if key != "recorded_at"}
        if comparable != previous_comparable:
            raise AppException(409, "FEEDBACK_KEY_REUSED", "같은 request_id에는 처음 저장한 확인 내용만 다시 보낼 수 있습니다.")
        return case
    if action == "금액 정정" and any(payload.get(name) is None for name in ("supply_amount", "vat_amount", "total_amount")):
        raise AppException(400, "CORRECTED_AMOUNT_REQUIRED", "금액 정정에는 공급가액·세액·공급대가를 모두 입력해 주세요.")
    signed_cancellation = issue.get("reason_code") == "CANCELLATION_RECONCILIATION_REQUIRED" and action == "금액 정정"
    corrected = [payload.get(name) for name in ("supply_amount", "vat_amount", "total_amount")]
    amount = payload.get("amount")
    if issue.get("reason_code") == "PG_SPREADSHEET_RECONCILIATION_REQUIRED":
        gross = issue["impact_amount"]
        if action == "누락 확인" and not issue.get("pg_classification_confirmed"):
            raise AppException(400, "PG_CLASSIFICATION_REQUIRED", "연결 문서에서 누락분의 과세·결제 구분을 먼저 확인해 주세요.")
        if action == "중복 확인" and amount != gross:
            raise AppException(400, "DUPLICATE_AMOUNT_REQUIRED", "전액 중복이면 원본 매출금액 전체를 입력해 주세요.")
        if action == "누락 확인" and (
            not all(isinstance(value, int) and value >= 0 for value in corrected)
            or not 0 < corrected[2] <= gross or corrected[0] + corrected[1] != corrected[2]
            or corrected[1] != corrected[0] * STANDARD_RATE // 100
        ):
            raise AppException(400, "INVALID_PG_MISSING_AMOUNT", "누락분의 공급가액·세액·공급대가를 입력하세요. 공급대가는 원본 매출금액 이하여야 합니다.")
        if action not in {"중복 확인", "누락 확인"}:
            raise AppException(400, "INVALID_FEEDBACK_ACTION", "전액 중복 또는 누락분을 확인해 주세요.")
    if amount is not None and (not isinstance(amount, int) or amount < 0):
        raise AppException(400, "INVALID_FEEDBACK_AMOUNT", "확인 금액은 0 이상의 원 단위로 입력해 주세요.")
    if any(value is not None and not isinstance(value, int) for value in corrected):
        raise AppException(400, "INVALID_FEEDBACK_AMOUNT", "정정 금액은 원 단위 정수로 입력해 주세요.")
    if any(value is not None and value < 0 for value in corrected) and not signed_cancellation:
        raise AppException(400, "INVALID_FEEDBACK_AMOUNT", "음수 금액은 원거래와 같은 신고기간의 취소·환불 정정에만 입력할 수 있습니다.")
    if signed_cancellation:
        if any(value is None for value in corrected):
            raise AppException(400, "CORRECTED_AMOUNT_REQUIRED", "취소·환불 정정에는 공급가액·세액·공급대가를 모두 입력해 주세요.")
        nonnegative = all(value >= 0 for value in corrected)
        nonpositive = all(value <= 0 for value in corrected)
        if not (nonnegative or nonpositive) or corrected[0] + corrected[1] != corrected[2]:
            raise AppException(400, "INVALID_CANCELLATION_AMOUNT", "취소·환불 정정 금액은 모두 양수 또는 모두 음수여야 하고 공급가액+세액=공급대가여야 합니다.")
        original_reference = (payload.get("original_reference") or "").strip()
        original_period = (payload.get("original_period") or "").strip()
        if not original_reference or original_period != period:
            raise AppException(400, "CANCELLATION_ORIGINAL_REQUIRED", f"원거래 승인번호와 같은 신고기간({period}) 확인이 필요합니다.")
    if issue.get("reason_code") == "POSSIBLE_SAME_SOURCE_DUPLICATE" and action == "중복 확인":
        if payload.get("amount") != issue.get("impact_amount"):
            raise AppException(400, "DUPLICATE_AMOUNT_REQUIRED", "중복 확인에는 중복 행 전체 금액을 입력해 주세요.")

    if issue.get("reason_code") in {"SOURCE_MISSING", "SOURCE_NEEDS_REVIEW", "SOURCE_EVIDENCE_MISSING"} and action == "해당 없음":
        source = issue.get("source")
        checks = _default_checks()
        checks.update(_loads(case.source_checks_json, {}))
        checks[source] = {"status": "해당 없음 확인", "query_start": None, "query_end": None,
                          "basis": None, "document_ids": [], "reason": evidence}
        case.source_checks_json = _json(checks)
    saved.append(feedback)
    case.feedback_json = _json(saved)
    session.add(case)
    session.commit()
    return refresh(session, user, period)


def finalize(session: Session, user: User, period: str, *, confirm_changed_sources: bool = False) -> SalesFilingWorkflow:
    case = refresh(session, user, period)
    issues = _loads(case.issues_json, [])
    if case.reconfirmation_required:
        unresolved = [item for item in issues if item.get("reason_code") != "CONFIRMED_INPUT_CHANGED"]
        if unresolved:
            raise AppException(409, "SALES_AGGREGATE_NOT_READY", unresolved[0]["question"])
        if not confirm_changed_sources:
            raise AppException(409, "SALES_AGGREGATE_RECONFIRMATION_REQUIRED", "확정 이후 바뀐 매출 근거와 새 합계를 검토하고 confirm_changed_sources=true로 다시 확정해 주세요.")
        case.reconfirmation_required = False
        case.status = "확정 가능"
        case.issues_json = "[]"
    if case.status != "확정 가능" or _loads(case.issues_json, []):
        first = _loads(case.issues_json, [])
        detail = first[0]["question"] if first else "매출 자료 검증을 마친 뒤 다시 확정해 주세요."
        raise AppException(409, "SALES_AGGREGATE_NOT_READY", detail)
    case.status = "확정"
    case.finalized_at = _now()
    case.revision += 1
    session.add(case)
    session.commit()
    session.refresh(case)
    return case


def public_result(case: SalesFilingWorkflow) -> dict[str, Any]:
    return {
        "id": case.id, "period": case.period, "business_number": case.business_number,
        "status": case.status, "revision": case.revision,
        "reconfirmation_required": case.reconfirmation_required,
        "finalized_at": case.finalized_at.isoformat() if case.finalized_at else None,
        "input_fingerprint": case.input_fingerprint,
        "source_statuses": _loads(case.source_checks_json, {}),
        "aggregate": _loads(case.aggregate_json, {}),
        "issues": _loads(case.issues_json, []),
        "history": _loads(case.history_json, []),
    }


def get_aggregate(session: Session, user: User, period: str, *, refresh_inputs: bool = True) -> dict[str, Any]:
    case = refresh(session, user, period) if refresh_inputs else _case(session, user.id, period)
    return public_result(case)
